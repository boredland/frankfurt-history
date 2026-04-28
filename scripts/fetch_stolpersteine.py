#!/usr/bin/env python3
"""Fetch Stolpersteine data: WFS for coordinates, Wayback crawler for content.

1. Fetches coordinates from Frankfurt's WFS endpoint
2. Crawls Stolperstein pages from Wayback Machine starting from the landing page,
   following links matching /standorte/* and /familien/* patterns
3. Translates German biographies to English via DeepL API

Usage:
    uv run scripts/fetch_stolpersteine.py                       # WFS only
    uv run scripts/fetch_stolpersteine.py --scrape              # + crawl from Wayback
    uv run scripts/fetch_stolpersteine.py --scrape --translate  # + translate via DeepL
"""

import html as html_mod
import json
import os
import re
import sys
import threading
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


# ---------- Config ----------

WFS_URL = (
    "https://geowebdienste.frankfurt.de/POI"
    "?service=WFS&version=1.1.0&request=GetFeature"
    "&srsName=EPSG%3A4326&typeName=Stolperstein"
)
REFERER = "https://geoportal.frankfurt.de/"

WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
STOLPERSTEINE_ROOT = "https://frankfurt.de/frankfurt-entdecken-und-erleben/stadtportrait/stadtgeschichte/stolpersteine"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_PATH = DATA_DIR / "stolpersteine-ffm.json"
SCRAPED_DIR = DATA_DIR / "stolpersteine-scraped"

DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")
DEEPL_URL = "https://api-free.deepl.com/v2/translate"

WORKERS = 4
MIN_PAGE_SIZE = 10000
UA = "Mozilla/5.0 (compatible; FrankfurtHistoryBot/1.0)"

NS = {
    "wfs": "http://www.opengis.net/wfs",
    "gml": "http://www.opengis.net/gml",
    "POI": "https://geowebdienste.frankfurt.de/POI",
}

LOCATION_RE = re.compile(r"/stolpersteine/[^/]+/standorte?/[^/]+$")
BIO_RE = re.compile(r"/stolpersteine/[^/]+/familien/[^/]+$")


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


def parse_wfs(xml_bytes: bytes) -> list[dict]:
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


def normalize_wfs(features: list[dict]) -> list[dict]:
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

def _submit_to_wayback(url: str):
    def _do():
        try:
            req = urllib.request.Request(
                f"https://web.archive.org/save/{url}",
                headers={"User-Agent": UA},
            )
            urllib.request.urlopen(req, timeout=30)
        except Exception:
            pass
    threading.Thread(target=_do, daemon=True).start()


def resolve_wayback_url(url: str) -> str | None:
    slug = url.split("/")[-1]
    cdx_url = (
        f"{WAYBACK_CDX}?url={urllib.parse.quote(url, safe='')}"
        f"&output=json&fl=timestamp,statuscode,length&filter=statuscode:200&limit=50"
    )
    req = urllib.request.Request(cdx_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            rows = json.loads(resp.read())
        for row in reversed(rows[1:]):
            ts, _status, length = row
            if int(length) >= MIN_PAGE_SIZE:
                return f"https://web.archive.org/web/{ts}/{url}"
        log(f"    CDX: {slug} — no snapshot >= {MIN_PAGE_SIZE}b")
    except Exception as e:
        log(f"    CDX: {slug} — {e}")
    _submit_to_wayback(url)
    return None


def fetch_wayback(url: str) -> str | None:
    slug = url.split("/")[-1]
    wb_url = resolve_wayback_url(url)
    if not wb_url:
        return None
    req = urllib.request.Request(wb_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        html = data.decode("utf-8", errors="replace")
        if "Just a moment" in html[:1000] or len(html) < 500:
            log(f"    Wayback: {slug} — CF challenge or too small")
            return None
        return html
    except Exception as e:
        log(f"    Wayback: {slug} — fetch failed: {e}")
        return None


# ---------- Link discovery ----------

def normalize_url(raw: str) -> str | None:
    """Normalize a URL found in HTML (may be Wayback-wrapped or relative)."""
    m = re.search(r"/web/\d+/(https?://[^\"]+)", raw)
    url = m.group(1).replace(":443", "") if m else raw
    if url.startswith("/"):
        url = "https://frankfurt.de" + url
    if not url.startswith("https://frankfurt.de"):
        return None
    return url.split("?")[0].split("#")[0].rstrip("/")


def discover_links(html: str) -> tuple[set[str], set[str]]:
    """Extract location and biography URLs from an HTML page."""
    locations = set()
    bios = set()
    for raw in re.findall(r'href="([^"]*stolpersteine[^"]*)"', html):
        url = normalize_url(raw)
        if not url:
            continue
        if BIO_RE.search(url):
            bios.add(url)
        elif LOCATION_RE.search(url):
            locations.add(url)
    return locations, bios


# ---------- Content extraction ----------

def extract_location(html: str) -> dict:
    result: dict = {"residents": [], "images": [], "bio_links": [], "laying_date": ""}

    article = re.search(
        r'class="contentBox _article[^"]*">(.*?)<div[^>]*class="contentBox(?! _article)',
        html, re.DOTALL,
    )
    if not article:
        return result
    content = article.group(1)

    match = re.search(r"wohnten?(.*?)Steinverlegung", content, re.DOTALL)
    if match:
        names = re.findall(r">([^<]+)</a>", match.group(1))
        result["residents"] = [html_mod.unescape(n.strip()) for n in names if n.strip()]

    _, bios = discover_links(html)
    result["bio_links"] = sorted(bios)

    date_match = re.search(r"Steinverlegung am:\s*</?\w+[^>]*>\s*(\d[\d.]+)", content, re.DOTALL)
    if date_match:
        result["laying_date"] = date_match.group(1).strip()

    for m in re.finditer(r'src="([^"]*stolpersteine[^"]*\.(?:jpg|png))', content, re.IGNORECASE):
        img_url = re.sub(r".*/web/\d+(?:im_)?/", "", m.group(1))
        if img_url.startswith("https://"):
            result["images"].append(img_url.split("?")[0])

    return result


def extract_biography(html: str) -> dict:
    result: dict = {"text": "", "images": []}

    article = re.search(
        r'class="contentBox _article[^"]*">(.*?)<div[^>]*class="contentBox(?! _article)',
        html, re.DOTALL,
    )
    if not article:
        return result
    content = article.group(1)

    text = re.sub(r"<[^>]+>", "\n", content)
    text = html_mod.unescape(text)
    text = re.sub(r"\n[ \t]*\n", "\n\n", text).strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    skip = ["inhalte teilen", "Internal Link", "Stadtplan", "Biographien", "Kontakt"]
    result["text"] = "\n\n".join(
        l for l in lines if not any(p in l for p in skip) and not l.startswith("©")
    )

    for m in re.finditer(r'src="([^"]*stolpersteine[^"]*\.(?:jpg|png))', content, re.IGNORECASE):
        img_url = re.sub(r".*/web/\d+(?:im_)?/", "", m.group(1))
        if img_url.startswith("https://"):
            result["images"].append(img_url.split("?")[0])

    return result


# ---------- Crawler ----------

def crawl(wfs_entries: list[dict], do_translate: bool = False):
    SCRAPED_DIR.mkdir(exist_ok=True)

    wfs_by_slug = {}
    for s in wfs_entries:
        if "url" in s:
            wfs_by_slug[s["url"].split("/")[-1]] = s

    already_scraped = {f.stem for f in SCRAPED_DIR.glob("*.json")}

    # Mark all known URLs as visited so we don't re-fetch them,
    # but collect all URLs they reference so we can find genuinely new ones
    known_urls: set[str] = set()
    for s in wfs_entries:
        if "url" in s:
            known_urls.add(s["url"])
    for f in SCRAPED_DIR.glob("*.json"):
        data = json.loads(f.read_text())
        if "url" in data:
            known_urls.add(data["url"])
        for bio_url in data.get("location", {}).get("bio_links", []):
            known_urls.add(bio_url)

    queue: list[str] = []
    visited: set[str] = set(known_urls)

    # Seed queue with un-scraped WFS URLs
    for s in wfs_entries:
        if "url" in s and s["url"].split("/")[-1] not in already_scraped:
            queue.append(s["url"])

    # Discover district index pages from the landing page
    log("Discovering pages from Stolpersteine landing page…")
    district_html = fetch_wayback(STOLPERSTEINE_ROOT)
    if district_html:
        for raw in re.findall(r'href="([^"]*stolpersteine-(?:in|im|an|am)[^"]*)"', district_html):
            url = normalize_url(raw)
            if url and url not in visited:
                visited.add(url)
                queue.append(url)

    log(f"  {len(already_scraped)} already scraped, {len(known_urls)} known URLs, {len(queue)} to crawl")

    ok = 0
    not_found = 0
    discovered = 0
    not_found_urls: list[str] = []
    processed = 0

    while queue:
        batch = []
        while queue and len(batch) < WORKERS:
            batch.append(queue.pop(0))

        def process_url(url: str) -> tuple[str, str | None, set[str], set[str]]:
            """Fetch a URL, return (url, html, new_locations, new_bios)."""
            html = fetch_wayback(url)
            if not html:
                return url, None, set(), set()
            locs, bios = discover_links(html)
            return url, html, locs, bios

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(process_url, url): url for url in batch}
            for future in as_completed(futures):
                url = futures[future]
                processed += 1
                try:
                    url, html, new_locs, new_bios = future.result()
                except Exception as e:
                    log(f"    ERROR {url.split('/')[-1]}: {e}")
                    continue

                if not html:
                    slug = url.split("/")[-1]
                    if LOCATION_RE.search(url):
                        not_found += 1
                        not_found_urls.append(url)
                        log(f"    MISS {slug}")
                    continue

                slug = url.split("/")[-1]

                # Enqueue newly discovered URLs
                for new_url in new_locs | new_bios:
                    if new_url not in visited:
                        visited.add(new_url)
                        queue.append(new_url)
                        discovered += 1

                # Process location pages
                if LOCATION_RE.search(url) and slug not in already_scraped:
                    wfs = wfs_by_slug.get(slug, {})
                    location = extract_location(html)

                    bios = []
                    for bio_url in location.get("bio_links", []):
                        bio_slug = bio_url.split("/")[-1]
                        # Check if we already fetched this bio in the queue
                        bio_html = fetch_wayback(bio_url)
                        if bio_html:
                            bio = extract_biography(bio_html)
                            bio["source_url"] = bio_url
                            if bio["text"]:
                                bios.append(bio)

                    result = {**wfs, "url": url, "location": location, "biographies": bios}
                    out_file = SCRAPED_DIR / f"{slug}.json"
                    out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
                    already_scraped.add(slug)
                    ok += 1
                    log(f"    OK {slug} — {len(bios)} bio(s)")

        if processed % 25 < WORKERS or not queue:
            total_scraped = len(list(SCRAPED_DIR.glob("*.json")))
            log(f"  Progress: {processed} processed, {ok} new, {not_found} missed, {discovered} discovered, {len(queue)} queued, {total_scraped} total files")

    total_scraped = len(list(SCRAPED_DIR.glob("*.json")))
    log(f"Crawl complete: {total_scraped} total files, {ok} new, {not_found} missed, {discovered} discovered")

    if not_found_urls:
        log(f"\n--- {len(not_found_urls)} location URLs not found ---")
        for url in sorted(not_found_urls):
            log(f"  {url}")

    if do_translate and DEEPL_API_KEY:
        translate_scraped()


# ---------- DeepL ----------

def translate_scraped():
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

    total_chars = sum(len(t) for _, _, t in to_translate)
    log(f"Translating {len(to_translate)} biographies via DeepL (~{total_chars // 1000}k chars)…")
    done = 0
    errors = 0
    chars_sent = 0
    for path, bio_idx, text in to_translate:
        en = translate_deepl(text)
        if en:
            data = json.loads(path.read_text())
            data["biographies"][bio_idx]["text_en"] = en
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            done += 1
            chars_sent += len(text)
        elif en is None and errors > 3:
            log(f"  DeepL: too many errors, stopping (quota likely exhausted)")
            break
        else:
            errors += 1
        if (done + errors) % 25 == 0:
            log(f"  DeepL progress: {done} translated, {errors} errors / {len(to_translate)} ({chars_sent // 1000}k chars)")
        time.sleep(1)
    log(f"DeepL done: {done} translated, {errors} errors, {chars_sent // 1000}k chars sent")


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
    except urllib.error.HTTPError as e:
        if e.code == 456:
            log("    DeepL: quota exhausted (456)")
        elif e.code == 429:
            log("    DeepL: rate limited (429), waiting 5s")
            time.sleep(5)
        else:
            log(f"    DeepL error: {e}")
        return None
    except Exception as e:
        log(f"    DeepL error: {e}")
        return None


# ---------- Main ----------

def main():
    do_scrape = "--scrape" in sys.argv
    do_translate = "--translate" in sys.argv

    log("Fetching Stolpersteine from frankfurt.de WFS…")
    xml_bytes = fetch_wfs()
    features = parse_wfs(xml_bytes)
    log(f"  Parsed {len(features)} Stolpersteine")

    normalized = normalize_wfs(features)
    with_url = sum(1 for s in normalized if "url" in s)
    log(f"  {with_url} with detail page URL")

    existing_count = 0
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text())
        existing_count = len(existing)

    if len(normalized) == 0 and existing_count > 0:
        log("  WFS returned 0 results — keeping existing data")
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
        crawl(normalized, do_translate)

    log("Done.")


if __name__ == "__main__":
    main()
