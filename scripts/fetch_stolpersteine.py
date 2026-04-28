#!/usr/bin/env python3
"""Fetch authoritative Stolpersteine data from Frankfurt's WFS + scrape detail pages.

1. Fetches the full Stolperstein dataset from Frankfurt's WFS endpoint
2. Scrapes location + biography pages from the Wayback Machine
3. Translates German biographies to English via DeepL API
4. Writes normalized JSON + per-location scraped content

Usage:
    uv run scripts/fetch_stolpersteine.py                       # WFS only
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

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_PATH = DATA_DIR / "stolpersteine-ffm.json"
SCRAPED_DIR = DATA_DIR / "stolpersteine-scraped"

DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")
DEEPL_URL = "https://api-free.deepl.com/v2/translate"

PARALLEL_WORKERS = 4

NS = {
    "wfs": "http://www.opengis.net/wfs",
    "gml": "http://www.opengis.net/gml",
    "POI": "https://geowebdienste.frankfurt.de/POI",
}

UA = "Mozilla/5.0 (compatible; FrankfurtHistoryBot/1.0)"

MIN_PAGE_SIZE = 10000


# ---------- WFS ----------

def fetch_wfs() -> bytes:
    req = urllib.request.Request(WFS_URL, headers={
        "Referer": REFERER,
        "Accept-Encoding": "identity",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            log(f"  WFS response: {resp.status}, {len(data)} bytes")
            return data
    except Exception as e:
        log(f"  WFS fetch failed: {e}")
        return b""


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

def resolve_wayback_url(url: str) -> str | None:
    """Get the best snapshot URL via CDX, filtering by size to skip CF challenge pages."""
    cdx_url = (
        f"{WAYBACK_CDX}?url={urllib.parse.quote(url, safe='')}"
        f"&output=json&fl=timestamp,statuscode,length&filter=statuscode:200&limit=50"
    )
    req = urllib.request.Request(cdx_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read())
        for row in reversed(rows[1:]):
            ts, _status, length = row
            if int(length) >= MIN_PAGE_SIZE:
                return f"https://web.archive.org/web/{ts}/{url}"
    except Exception:
        pass
    return None


def _fetch_html(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        html = data.decode("utf-8", errors="replace")
        if "Just a moment" in html[:1000] or len(html) < 500:
            return None
        return html
    except Exception:
        return None


def fetch_page(url: str) -> tuple[str | None, str]:
    """Fetch a page from the Wayback Machine. Returns (html, source)."""
    wb_url = resolve_wayback_url(url)
    if not wb_url:
        return None, "no snapshot"
    html = _fetch_html(wb_url)
    if html:
        return html, "wayback"
    return None, "fetch failed"


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


def scrape_one(item: dict) -> dict | str:
    """Returns scraped dict, or a status string explaining the miss."""
    slug = item["url"].split("/")[-1]
    out_file = SCRAPED_DIR / f"{slug}.json"

    if out_file.exists():
        return SKIP

    html, source = fetch_page(item["url"])
    if not html:
        log(f"    MISS {slug} — {source}")
        return NOT_FOUND

    location = extract_location_page(html)

    bios = []
    for bio_link in location.get("bio_links", []):
        bio_html, _ = fetch_page(bio_link)
        if not bio_html:
            continue
        bio = extract_biography(bio_html)
        bio["source_url"] = bio_link
        bios.append(bio)

    result = {**item, "location": location, "biographies": bios}
    out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    log(f"    OK {slug} via {source} — {len(bios)} bio(s), {len(location.get('residents', []))} residents")
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

    log(f"Scraping detail pages via Wayback Machine ({PARALLEL_WORKERS} workers)…")
    log(f"  {len(items)} total, {len(items) - len(to_scrape)} cached, {len(to_scrape)} to fetch")

    not_found_urls: list[str] = []
    BATCH_SIZE = 25

    if to_scrape:
        done = 0
        ok = 0
        not_found = 0
        errors = 0
        total = len(to_scrape)

        for batch_start in range(0, total, BATCH_SIZE):
            batch = to_scrape[batch_start : batch_start + BATCH_SIZE]
            with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
                futures = {
                    pool.submit(scrape_one, item): item
                    for item in batch
                }
                for future in as_completed(futures):
                    done += 1
                    item = futures[future]
                    try:
                        result = future.result()
                        if result == SKIP:
                            ok += 1
                        elif result == NOT_FOUND:
                            not_found += 1
                            not_found_urls.append(item["url"])
                        elif isinstance(result, dict):
                            ok += 1
                        else:
                            errors += 1
                    except Exception as e:
                        errors += 1
                        log(f"  ERROR {item['url'].split('/')[-1]}: {e}")

            log(f"  Batch {batch_start // BATCH_SIZE + 1}: {done}/{total} — {ok} ok, {not_found} not found, {errors} errors")

    total_scraped = len(list(SCRAPED_DIR.glob("*.json")))
    log(f"Scraping complete: {total_scraped} total files")

    if not_found_urls:
        log(f"\n--- {len(not_found_urls)} URLs not found in Wayback Machine ---")
        for url in sorted(not_found_urls):
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

    existing_count = 0
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text())
        existing_count = len(existing)

    if len(normalized) == 0 and existing_count > 0:
        log("  WFS returned 0 results — keeping existing data, skipping write")
        normalized = existing
    else:
        OUT_PATH.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n")
        log(f"  Written to {OUT_PATH}")
        if existing_count:
            delta = len(normalized) - existing_count
            if delta > 0:
                log(f"  +{delta} new since last run")
            elif delta < 0:
                log(f"  {delta} removed since last run")

    if do_scrape:
        if do_translate and not DEEPL_API_KEY:
            log("Warning: --translate requested but DEEPL_API_KEY not set")
        scrape_content(normalized, do_translate)

    log("Done.")


if __name__ == "__main__":
    main()
