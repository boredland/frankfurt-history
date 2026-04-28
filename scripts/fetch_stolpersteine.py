#!/usr/bin/env python3
"""Fetch authoritative Stolpersteine data from Frankfurt's WFS service.

The City of Frankfurt publishes Stolperstein locations via a WFS endpoint
on geowebdienste.frankfurt.de. This script fetches the full dataset,
parses the GML response, and writes a normalized JSON file.

Usage:
    uv run scripts/fetch_stolpersteine.py
"""

import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

WFS_URL = (
    "https://geowebdienste.frankfurt.de/POI"
    "?service=WFS&version=1.1.0&request=GetFeature"
    "&srsName=EPSG%3A4326&typeName=Stolperstein"
)
REFERER = "https://geoportal.frankfurt.de/"

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "stolpersteine-ffm.json"

NS = {
    "wfs": "http://www.opengis.net/wfs",
    "gml": "http://www.opengis.net/gml",
    "POI": "https://geowebdienste.frankfurt.de/POI",
}


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


def main():
    print("Fetching Stolpersteine from frankfurt.de WFS…")
    xml_bytes = fetch_wfs()
    features = parse_features(xml_bytes)
    print(f"  Parsed {len(features)} Stolpersteine")

    normalized = normalize(features)
    with_url = sum(1 for s in normalized if "url" in s)
    print(f"  {with_url} with detail page URL")

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


if __name__ == "__main__":
    main()
