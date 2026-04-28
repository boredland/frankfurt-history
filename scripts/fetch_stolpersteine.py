#!/usr/bin/env python3
"""Fetch authoritative Stolpersteine data from Frankfurt's WFS + Wayback Machine.

1. Fetches the full Stolperstein dataset from Frankfurt's WFS endpoint
2. Checks Wayback Machine coverage, submits missing pages for archival
3. Fetches location + biography pages from Wayback (parallel) for content extraction
4. Translates German biographies to English via DeepL API
5. Writes normalized JSON + per-location scraped content

Usage:
    uv run scripts/fetch_stolpersteine.py                       # WFS + Wayback check
    uv run scripts/fetch_stolpersteine.py --scrape              # + scrape from Wayback
    uv run scripts/fetch_stolpersteine.py --scrape --translate  # + translate via DeepL
"""

import html as html_mod
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_start_time = time.monotonic()

def log(msg: str):
    elapsed = time.monotonic() - _start_time
    m, s = divmod(int(elapsed), 60)
    print(f"[{m:02d}:{s:02d}] {msg}", flush=True)

WFS_URL = (
    "https://geowebdienste.frankfurt.de/POI"
    "?service=WFS&version=1.1.0&request=GetFeature"
    "&srsName=EPSG%3A4326&typeName=Stolperstein"
)
REFERER = "https://geoportal.frankfurt.de/"

WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK_SAVE = "https://web.archive.org/save/"
WAYBACK_AVAIL = "https://archive.org/wayback/available"

SCRAPFLY_API_KEY = os.environ.get("SCRAPFLY_API_KEY", "")
SCRAPFLY_URL = "https://api.scrapfly.io/scrape"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_PATH = DATA_DIR / "stolpersteine-ffm.json"
SCRAPED_DIR = DATA_DIR / "stolpersteine-scraped"

DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")
DEEPL_URL = "https://api-free.deepl.com/v2/translate"

PARALLEL_WORKERS = 8

NS = {
    "wfs": "http://www.opengis.net/wfs",
    "gml": "http://www.opengis.net/gml",
    "POI": "https://geowebdienste.frankfurt.de/POI",
}

UA = "Mozilla/5.0 (compatible; FrankfurtHistoryBot/1.0)"


# ---------- WFS ----------

def fetch_wfs() -> bytes:
    req = urllib.request.Request(WFS_URL, headers={"Referer": REFERER})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def parse_features(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    results = []
    for feat in root.findall(".//POI:Stolperstein", NS):
        entry: dict = {}
        for child in feat:
            tag = child.tag.split("}")[1] if "}" in child.tag else child.tag
            if tag == "SHAPE":
                pos = child.find(".//gml:pos", NS)
                if pos is not None and pos.text:
                    parts = pos.text.strip().split()
                    if len(parts) == 2:
                        entry["lat"] = round(float(parts[0]), 7)
                        entry["lng"] = round(float(parts[1]), 7)
            elif child.text:
                entry[tag] = child.text.strip()
        if "lat" in entry and "lng" in entry:
            results.append(entry)
    return results


def normalize(features: list[dict]) -> list[dict]:
    out = []
    for f in features:
        item = {
            "name": f.get("Bezeichnung", ""),
            "address": f.get("Adresse", ""),
            "street": f.get("Strasse", ""),
            "house_number": f.get("Hausnummer", ""),
            "zip": f.get("Postleitzahl", ""),
            "lat": f["lat"],
            "lng": f["lng"],
        }
        url = f.get("URL")
        if url:
            item["url"] = url
        out.append(item)
    return sorted(out, key=lambda x: x["address"])


# ---------- Wayback Machine ----------

def get_archived_urls() -> set[str]:
    params = (
        "?url=frankfurt.de/frankfurt-entdecken-und-erleben/stadtportrait/"
        "stadtgeschichte/stolpersteine/"
        "&matchType=prefix&collapse=urlkey&output=text&fl=original"
        "&filter=statuscode:200"
    )
    req = urllib.request.Request(WAYBACK_CDX + params, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            text = resp.read().decode()
        urls = set()
        for line in text.strip().splitlines():
            url = line.strip().replace("http://", "https://").rstrip("/")
            if "/standorte/" in url or "/standort/" in url:
                urls.add(url)
        return urls
    except Exception as e:
        log(f"  Warning: CDX query failed: {e}")
        return set()


def submit_to_wayback(urls: list[str]) -> int:
    submitted = 0
    for url in urls:
        try:
            req = urllib.request.Request(
                WAYBACK_SAVE + url, headers={"User-Agent": UA}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status in (200, 302):
                    submitted += 1
            time.sleep(2)
        except Exception:
            pass
    return submitted


def resolve_wayback_urls(url: str) -> list[str]:
    """Get snapshot URLs for a page, newest first. Uses Availability API + CDX fallback."""
    urls = []
    api_url = f"{WAYBACK_AVAIL}?url={urllib.parse.quote(url, safe='')}"
    req = urllib.request.Request(api_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        snap = data.get("archived_snapshots", {}).get("closest", {})
        if snap.get("available") and snap.get("status") == "200":
            urls.append(snap["url"])
    except Exception:
        pass

    cdx_url = (
        f"{WAYBACK_CDX}?url={urllib.parse.quote(url, safe='')}"
        "&output=json&fl=timestamp,statuscode&filter=statuscode:200&limit=5"
    )
    req = urllib.request.Request(cdx_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read())
        for row in reversed(rows[1:]):
            ts = row[0]
            candidate = f"https://web.archive.org/web/{ts}/{url}"
            if candidate not in urls:
                urls.append(candidate)
    except Exception:
        pass

    return urls


def _fetch_html(wb_url: str, retries: int = 3) -> str | None:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(wb_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = resp.read()
            html = data.decode("utf-8", errors="replace")
            if "Just a moment" in html[:1000]:
                return None
            if len(html) < 500:
                return None
            return html
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                log(f"    Wayback fetch failed: {e}")
                return None


def fetch_wayback(url: str) -> str | None:
    for wb_url in resolve_wayback_urls(url):
        html = _fetch_html(wb_url, retries=1)
        if html:
            return html
    return None


def fetch_scrapfly(url: str) -> str | None:
    if not SCRAPFLY_API_KEY:
        return None
    params = urllib.parse.urlencode({
        "key": SCRAPFLY_API_KEY,
        "url": url,
        "asp": "true",
        "render_js": "true",
        "country": "de",
    })
    req = urllib.request.Request(
        f"{SCRAPFLY_URL}?{params}",
        headers={"User-Agent": UA, "Accept-Encoding": "identity"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        content = data.get("result", {}).get("content", "")
        status = data.get("result", {}).get("status_code", 0)
        if status == 200 and len(content) > 500:
            return content
    except Exception as e:
        log(f"    Scrapfly error: {e}")
    return None


def fetch_page(url: str) -> str | None:
    """Fetch a page: try Wayback first, fall back to Scrapfly."""
    html = fetch_wayback(url)
    if html:
        return html
    html = fetch_scrapfly(url)
    if html:
        return html
    return None


# ---------- Content extraction ----------

def extract_location_page(html_content: str) -> dict:
    result: dict = {"residents": [], "images": [], "bio_links": [], "laying_date": ""}

    article = re.search(
        r'class="contentBox _article[^"]*">(.*?)<div[^>]*class="contentBox(?! _article)',
        html_content, re.DOTALL,
    )
    if not article:
        return result

    content = article.group(1)

    residents_match = re.search(r"Hier wohnten?(.*?)Steinverlegung", content, re.DOTALL)
    if residents_match:
        chunk = residents_match.group(1)
        names = re.findall(r">([^<]+)</a>", chunk)
        result["residents"] = [html_mod.unescape(n.strip()) for n in names if n.strip()]
        bio_links = re.findall(r'href="([^"]+)"', chunk)
        for bl in bio_links:
            m = re.search(r"/web/\d+/(https?://[^\"]+)", bl)
            if m:
                result["bio_links"].append(m.group(1).replace(":443", ""))

    date_match = re.search(r"Steinverlegung am:\s*</?\w+[^>]*>\s*(\d[\d.]+)", content, re.DOTALL)
    if date_match:
        result["laying_date"] = date_match.group(1).strip()

    for m in re.finditer(r'src="([^"]*stolpersteine[^"]*\.(?:jpg|png))', content, re.IGNORECASE):
        img_url = re.sub(r".*/web/\d+(?:im_)?/", "", m.group(1))
        if img_url.startswith("https://"):
            result["images"].append(img_url.split("?")[0])

    return result


def extract_biography(html_content: str) -> dict:
    result: dict = {"text": "", "images": []}

    article = re.search(
        r'class="contentBox _article[^"]*">(.*?)<div[^>]*class="contentBox(?! _article)',
        html_content, re.DOTALL,
    )
    if not article:
        return result

    content = article.group(1)

    text = re.sub(r"<[^>]+>", "\n", content)
    text = html_mod.unescape(text)
    text = re.sub(r"\n[ \t]*\n", "\n\n", text).strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    bio_lines = []
    skip_patterns = ["inhalte teilen", "Internal Link", "Stadtplan", "Biographien", "Kontakt"]
    for line in lines:
        if any(p in line for p in skip_patterns):
            continue
        if line.startswith("©"):
            continue
        bio_lines.append(line)

    result["text"] = "\n\n".join(bio_lines)

    for m in re.finditer(r'src="([^"]*stolpersteine[^"]*\.(?:jpg|png))', content, re.IGNORECASE):
        img_url = re.sub(r".*/web/\d+(?:im_)?/", "", m.group(1))
        if img_url.startswith("https://"):
            result["images"].append(img_url.split("?")[0])

    return result


# ---------- DeepL ----------

def translate_deepl(text: str, target_lang: str = "EN") -> str | None:
    if not DEEPL_API_KEY:
        return None
    data = urllib.parse.urlencode({
        "text": text,
        "source_lang": "DE",
        "target_lang": target_lang,
    }).encode()
    req = urllib.request.Request(DEEPL_URL, data=data, headers={
        "Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return result["translations"][0]["text"]
    except Exception as e:
        log(f"    DeepL error: {e}")
        return None


# ---------- Scraping pipeline ----------

SKIP = "skip"
NOT_FOUND = "not_found"
FETCH_FAILED = "fetch_failed"


def scrape_one(item: dict) -> dict | str:
    """Returns scraped dict, or a status string explaining the miss."""
    slug = item["url"].split("/")[-1]
    out_file = SCRAPED_DIR / f"{slug}.json"

    if out_file.exists():
        return SKIP

    html = fetch_page(item["url"])
    if not html:
        return NOT_FOUND

    location = extract_location_page(html)

    bios = []
    for bio_link in location.get("bio_links", []):
        bio_html = fetch_page(bio_link)
        if not bio_html:
            continue
        bio = extract_biography(bio_html)
        bio["source_url"] = bio_link
        bios.append(bio)

    result = {**item, "location": location, "biographies": bios}
    out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return result


def translate_scraped():
    """Batch-translate all scraped biographies that lack English text."""
    files = sorted(SCRAPED_DIR.glob("*.json"))
    to_translate = []
    for f in files:
        data = json.loads(f.read_text())
        for i, bio in enumerate(data.get("biographies", [])):
            if bio.get("text") and not bio.get("text_en"):
                to_translate.append((f, i, bio["text"]))

    if not to_translate:
        log("All biographies already translated")
        return

    log(f"Translating {len(to_translate)} biographies via DeepL…")
    done = 0
    errors = 0
    for path, bio_idx, text in to_translate:
        en = translate_deepl(text)
        if en:
            data = json.loads(path.read_text())
            data["biographies"][bio_idx]["text_en"] = en
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            done += 1
        else:
            errors += 1
        if (done + errors) % 25 == 0:
            log(f"  DeepL progress: {done} translated, {errors} errors / {len(to_translate)} total")
    log(f"DeepL done: {done} translated, {errors} errors")


def scrape_content(stolpersteine: list[dict], do_translate: bool = False):
    SCRAPED_DIR.mkdir(exist_ok=True)

    items = [s for s in stolpersteine if "url" in s]
    to_scrape = [
        s for s in items
        if not (SCRAPED_DIR / f"{s['url'].split('/')[-1]}.json").exists()
    ]

    log(f"Scraping from Wayback Machine ({PARALLEL_WORKERS} workers)…")
    log(f"  {len(items)} total, {len(items) - len(to_scrape)} cached, {len(to_scrape)} to fetch")

    not_archived_urls: list[str] = []
    fetch_failed_urls: list[str] = []
    if to_scrape:
        done = 0
        ok = 0
        not_archived = 0
        fetch_failed = 0
        errors = 0
        total = len(to_scrape)
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
            futures = {
                pool.submit(scrape_one, item): item
                for item in to_scrape
            }
            for future in as_completed(futures):
                done += 1
                item = futures[future]
                try:
                    result = future.result()
                    if result == SKIP:
                        ok += 1
                    elif result == NOT_FOUND:
                        not_archived += 1
                        not_archived_urls.append(item["url"])
                    elif result == FETCH_FAILED:
                        fetch_failed += 1
                        fetch_failed_urls.append(item["url"])
                    elif isinstance(result, dict):
                        ok += 1
                    else:
                        errors += 1
                except Exception as e:
                    errors += 1
                    log(f"  ERROR {item['url'].split('/')[-1]}: {e}")
                if done % 25 == 0 or done == total:
                    log(f"  Wayback progress: {done}/{total} — {ok} ok, {not_archived} not archived, {fetch_failed} fetch failed, {errors} errors")

    total_scraped = len(list(SCRAPED_DIR.glob("*.json")))
    log(f"Scraping complete: {total_scraped} total files")

    if not_archived_urls:
        log(f"\n--- {len(not_archived_urls)} URLs not archived (no Wayback snapshot exists) ---")
        for url in sorted(not_archived_urls):
            log(f"  {url}")
    if fetch_failed_urls:
        log(f"\n--- {len(fetch_failed_urls)} URLs archived but fetch failed ---")
        for url in sorted(fetch_failed_urls):
            log(f"  {url}")

    if do_translate and DEEPL_API_KEY:
        translate_scraped()


# ---------- Main ----------

def main():
    do_scrape = "--scrape" in sys.argv
    do_translate = "--translate" in sys.argv

    log("Fetching Stolpersteine from frankfurt.de WFS…")
    xml_bytes = fetch_wfs()
    features = parse_features(xml_bytes)
    log(f"  Parsed {len(features)} Stolpersteine")

    normalized = normalize(features)
    with_url = sum(1 for s in normalized if "url" in s)
    log(f"  {with_url} with detail page URL")

    our_urls = {
        s["url"].replace("http://", "https://").rstrip("/")
        for s in normalized
        if "url" in s
    }

    log("Checking Wayback Machine coverage…")
    archived = get_archived_urls()
    if archived:
        missing = sorted(our_urls - archived)
        log(f"  {len(archived)} archived, {len(missing)} missing")
        if missing:
            log(f"  Submitting {len(missing)} pages to Wayback Machine…")
            ok = submit_to_wayback(missing)
            log(f"  Submitted {ok}/{len(missing)}")
    else:
        log("  Could not check coverage (CDX unavailable)")

    existing_count = 0
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text())
        existing_count = len(existing)

    OUT_PATH.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n")
    log(f"  Written to {OUT_PATH}")

    if existing_count:
        delta = len(normalized) - existing_count
        if delta > 0:
            log(f"  +{delta} new since last run")
        elif delta < 0:
            log(f"  {delta} removed since last run")
        else:
            log("  No change in count")

    if do_scrape:
        if do_translate and not DEEPL_API_KEY:
            log("Warning: --translate requested but DEEPL_API_KEY not set")
        scrape_content(normalized, do_translate)

    log("Done.")


if __name__ == "__main__":
    main()
