#!/usr/bin/env python3
"""Reverse geocode POI coordinates to street addresses via Photon (Komoot).

Strategy:
1. Reverse geocode via Photon — best precision for coordinates
2. If no house number returned, forward geocode the POI's subtitle
   (which often contains the real street address) near the coordinates
3. Cache results permanently in data/addresses.json

Uses Photon (https://photon.komoot.io) — no API key required.
"""

import json
import re
import sys
import time
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_PATH = DATA_DIR / "addresses.json"
PHOTON_REVERSE = "https://photon.komoot.io/reverse"
PHOTON_FORWARD = "https://photon.komoot.io/api"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "FrankfurtHistoryApp/1.0 (https://history.jonas-strassel.de)"

STREET_RE = re.compile(
    r"(?:straße|strasse|weg|platz|allee|gasse|ring|anlage|pfad|ufer|damm|chaussee)",
    re.IGNORECASE,
)


def load_cache() -> dict[str, str]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache: dict[str, str]):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n")


def coord_key(lat: float, lng: float) -> str:
    return f"{lat:.6f},{lng:.6f}"


def parse_poi(path: Path) -> tuple[float, float, str] | None:
    text = path.read_text()
    if not text.startswith("---"):
        return None
    end = text.index("---", 3)
    fm = text[3:end]
    m = re.search(r"coordinates:\s*\[([\d.]+),\s*([\d.]+)\]", fm)
    if not m:
        return None
    lat, lng = float(m.group(1)), float(m.group(2))
    if not (49.5 < lat < 50.5 and 8.0 < lng < 9.5):
        return None
    sub_m = re.search(r'subtitle:\s*"?([^"\n]+)', fm)
    subtitle = sub_m.group(1).strip() if sub_m else ""
    return lat, lng, subtitle


def format_addr(props: dict) -> str:
    street = props.get("street", "")
    house = props.get("housenumber", "")
    if street and house:
        return f"{street} {house}"
    return ""


def photon_get(client: httpx.Client, url: str, params: dict) -> dict:
    for attempt in range(3):
        r = client.get(url, params=params)
        if r.status_code == 403:
            wait = 5 * (attempt + 1)
            print(f"    Rate limited, waiting {wait}s...", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    return {}


def nominatim_reverse(client: httpx.Client, lat: float, lng: float) -> str:
    try:
        r = client.get(
            NOMINATIM_REVERSE,
            params={"lat": lat, "lon": lng, "format": "jsonv2", "addressdetails": 1, "zoom": 18},
            headers={"User-Agent": USER_AGENT},
        )
        if r.status_code == 429:
            time.sleep(5)
            return ""
        r.raise_for_status()
        addr = r.json().get("address", {})
        road = addr.get("road", addr.get("pedestrian", ""))
        house = addr.get("house_number", "")
        if road and house:
            return f"{road} {house}"
        return ""
    except Exception:
        return ""


def reverse_geocode(client: httpx.Client, lat: float, lng: float, subtitle: str) -> str:
    try:
        # 1. Photon reverse
        data = photon_get(client, PHOTON_REVERSE, {"lat": lat, "lon": lng})
        features = data.get("features", [])
        if features:
            addr = format_addr(features[0].get("properties", {}))
            if addr:
                return addr

        # 2. Nominatim reverse (fallback)
        time.sleep(1.5)
        addr = nominatim_reverse(client, lat, lng)
        if addr:
            return addr

        # 3. Photon forward geocode the subtitle
        if subtitle and STREET_RE.search(subtitle):
            time.sleep(1.5)
            data2 = photon_get(
                client,
                PHOTON_FORWARD,
                {
                    "q": f"{subtitle}, Frankfurt am Main",
                    "lat": lat,
                    "lon": lng,
                    "limit": 1,
                },
            )
            features2 = data2.get("features", [])
            if features2:
                addr2 = format_addr(features2[0].get("properties", {}))
                if addr2:
                    return addr2

        return ""
    except Exception as e:
        print(f"    Error: {e}", flush=True)
        return ""


def main():
    cache = load_cache()

    unique_coords: dict[str, tuple[float, float, str]] = {}
    for source_dir in [DATA_DIR] + (
        [DATA_DIR / "de"] if (DATA_DIR / "de").is_dir() else []
    ):
        for theme_dir in sorted(source_dir.iterdir()):
            if not theme_dir.is_dir() or theme_dir.name in ("images", "de", "en"):
                continue
            for poi_path in sorted(theme_dir.glob("*.md")):
                if poi_path.name.startswith("_"):
                    continue
                result = parse_poi(poi_path)
                if result:
                    lat, lng, subtitle = result
                    key = coord_key(lat, lng)
                    if key not in unique_coords:
                        unique_coords[key] = (lat, lng, subtitle)

    uncached = {k: v for k, v in unique_coords.items() if k not in cache}

    BATCH_SIZE = 100

    print(f"Unique coordinates: {len(unique_coords)}", flush=True)
    print(f"Already cached: {len(unique_coords) - len(uncached)}", flush=True)
    print(f"Need to geocode: {len(uncached)} (processing max {BATCH_SIZE} per run)", flush=True)

    if not uncached:
        print("Cache is up to date", flush=True)
        return

    batch = dict(list(uncached.items())[:BATCH_SIZE])
    print(f"Geocoding batch of {len(batch)}...", flush=True)

    client = httpx.Client(timeout=15)
    success = 0
    for i, (key, (lat, lng, subtitle)) in enumerate(batch.items()):
        addr = reverse_geocode(client, lat, lng, subtitle)
        cache[key] = addr
        if addr:
            success += 1
        print(f"  {i + 1}/{len(batch)}: {addr or '(empty)'}", flush=True)
        save_cache(cache)
        time.sleep(2)
    client.close()
    save_cache(cache)
    remaining = len(uncached) - len(batch)
    print(f"Batch done: {success}/{len(batch)} with addresses, {remaining} remaining", flush=True)


if __name__ == "__main__":
    main()
