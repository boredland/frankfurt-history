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

WFS_URL = (
    "https://geowebdienste.frankfurt.de/POI"
    "?service=WFS&version=1.1.0&request=GetFeature"
    "&srsName=EPSG%3A4326&typeName=Stolperstein"
)
REFERER = "https://geoportal.frankfurt.de/"

WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK_SAVE = "https://web.archive.org/save/"
WAYBACK_WEB = "http://web.archive.org/web/2025/"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_PATH = DATA_DIR / "stolpersteine-ffm.json"
SCRAPED_DIR = DATA_DIR / "stolpersteine-scraped"

DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")
DEEPL_URL = "https://api-free.deepl.com/v2/translate"

PARALLEL_WORKERS = 15

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
        print(f"  Warning: CDX query failed: {e}")
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


def fetch_wayback(url: str) -> str | None:
    wb_url = WAYBACK_WEB + url
    req = urllib.request.Request(wb_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        html = data.decode("utf-8", errors="replace")
        if "Just a moment" in html[:1000]:
            return None
        return html
    except Exception:
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
        "auth_key": DEEPL_API_KEY,
        "text": text,
        "source_lang": "DE",
        "target_lang": target_lang,
    }).encode()
    req = urllib.request.Request(DEEPL_URL, data=data, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return result["translations"][0]["text"]
    except Exception as e:
        print(f"    DeepL error: {e}")
        return None


# ---------- Scraping pipeline ----------

def scrape_one(item: dict) -> dict | None:
    """Scrape one Stolperstein location + its biographies from Wayback."""
    slug = item["url"].split("/")[-1]
    out_file = SCRAPED_DIR / f"{slug}.json"

    if out_file.exists():
        return None

    html = fetch_wayback(item["url"])
    if not html:
        return None

    location = extract_location_page(html)

    bios = []
    for bio_link in location.get("bio_links", []):
        bio_html = fetch_wayback(bio_link)
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
        print("  All biographies already translated")
        return

    print(f"  Translating {len(to_translate)} biographies via DeepL…")
    done = 0
    for path, bio_idx, text in to_translate:
        en = translate_deepl(text)
        if en:
            data = json.loads(path.read_text())
            data["biographies"][bio_idx]["text_en"] = en
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            done += 1
        if done % 10 == 0 and done > 0:
            print(f"    {done}/{len(to_translate)} translated")
    print(f"  {done}/{len(to_translate)} translated")


def scrape_content(stolpersteine: list[dict], do_translate: bool = False):
    SCRAPED_DIR.mkdir(exist_ok=True)

    items = [s for s in stolpersteine if "url" in s]
    to_scrape = [
        s for s in items
        if not (SCRAPED_DIR / f"{s['url'].split('/')[-1]}.json").exists()
    ]

    print(f"\nScraping from Wayback Machine ({PARALLEL_WORKERS} workers)…")
    print(f"  {len(items)} total, {len(items) - len(to_scrape)} cached, {len(to_scrape)} to fetch")

    if to_scrape:
        done = 0
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
            futures = {
                pool.submit(scrape_one, item): item
                for item in to_scrape
            }
            for future in as_completed(futures):
                done += 1
                item = futures[future]
                slug = item["url"].split("/")[-1]
                try:
                    result = future.result()
                    if result:
                        n_bios = len(result.get("biographies", []))
                        print(f"  [{done}/{len(to_scrape)}] {slug} — {n_bios} bio(s)")
                    else:
                        print(f"  [{done}/{len(to_scrape)}] {slug} — not in archive")
                except Exception as e:
                    print(f"  [{done}/{len(to_scrape)}] {slug} — error: {e}")

    total_scraped = len(list(SCRAPED_DIR.glob("*.json")))
    print(f"  {total_scraped} total scraped files")

    if do_translate and DEEPL_API_KEY:
        translate_scraped()


# ---------- Main ----------

def main():
    do_scrape = "--scrape" in sys.argv
    do_translate = "--translate" in sys.argv

    print("Fetching Stolpersteine from frankfurt.de WFS…")
    xml_bytes = fetch_wfs()
    features = parse_features(xml_bytes)
    print(f"  Parsed {len(features)} Stolpersteine")

    normalized = normalize(features)
    with_url = sum(1 for s in normalized if "url" in s)
    print(f"  {with_url} with detail page URL")

    our_urls = {
        s["url"].replace("http://", "https://").rstrip("/")
        for s in normalized
        if "url" in s
    }

    print("Checking Wayback Machine coverage…")
    archived = get_archived_urls()
    if archived:
        missing = sorted(our_urls - archived)
        print(f"  {len(archived)} archived, {len(missing)} missing")
        if missing:
            print(f"  Submitting {len(missing)} pages to Wayback Machine…")
            ok = submit_to_wayback(missing)
            print(f"  Submitted {ok}/{len(missing)}")
    else:
        print("  Could not check coverage (CDX unavailable)")

    existing_count = 0
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text())
        existing_count = len(existing)

    OUT_PATH.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n")
    print(f"  Written to {OUT_PATH}")

    if existing_count:
        delta = len(normalized) - existing_count
        if delta > 0:
            print(f"  +{delta} new since last run")
        elif delta < 0:
            print(f"  {delta} removed since last run")
        else:
            print("  No change in count")

    if do_scrape:
        if do_translate and not DEEPL_API_KEY:
            print("Warning: --translate requested but DEEPL_API_KEY not set")
        scrape_content(normalized, do_translate)


if __name__ == "__main__":
    main()
