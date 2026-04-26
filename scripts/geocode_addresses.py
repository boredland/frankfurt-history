#!/usr/bin/env python3
"""Reverse geocode POI coordinates to street addresses via Nominatim.

Reads coordinates from data/de/<theme>/*.md frontmatter, reverse geocodes
each unique coordinate pair, and caches results in data/addresses.json.
Only calls the API for coordinates not already cached.

Rate-limited to 1 req/sec per Nominatim usage policy.
The cache file is committed to git and persists across runs.
"""

import json
import re
import sys
import time
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_PATH = DATA_DIR / "addresses.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "FrankfurtHistoryApp/1.0 (https://history.jonas-strassel.de)"


def load_cache() -> dict[str, str]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache: dict[str, str]):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n")


def coord_key(lat: float, lng: float) -> str:
    return f"{lat:.6f},{lng:.6f}"


def parse_coordinates(path: Path) -> tuple[float, float] | None:
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
    return lat, lng


def reverse_geocode(client: httpx.Client, lat: float, lng: float) -> str:
    try:
        r = client.get(
            NOMINATIM_URL,
            params={
                "lat": lat,
                "lon": lng,
                "format": "jsonv2",
                "addressdetails": 1,
                "zoom": 18,
            },
        )
        r.raise_for_status()
        data = r.json()
        addr = data.get("address", {})
        road = addr.get("road", addr.get("pedestrian", addr.get("footway", "")))
        house = addr.get("house_number", "")
        if road and house:
            return f"{road} {house}"
        return road or ""
    except Exception as e:
        print(f"  Error geocoding {lat},{lng}: {e}")
        return ""


def main():
    cache = load_cache()

    unique_coords: dict[str, tuple[float, float]] = {}
    for theme_dir in sorted(DATA_DIR.iterdir()):
        if not theme_dir.is_dir() or theme_dir.name in ("images", "de", "en"):
            continue
        for poi_path in sorted(theme_dir.glob("*.md")):
            if poi_path.name.startswith("_"):
                continue
            coords = parse_coordinates(poi_path)
            if coords:
                key = coord_key(coords[0], coords[1])
                unique_coords[key] = coords

    de_dir = DATA_DIR / "de"
    if de_dir.is_dir():
        for theme_dir in sorted(de_dir.iterdir()):
            if not theme_dir.is_dir():
                continue
            for poi_path in sorted(theme_dir.glob("*.md")):
                if poi_path.name.startswith("_"):
                    continue
                coords = parse_coordinates(poi_path)
                if coords:
                    key = coord_key(coords[0], coords[1])
                    unique_coords[key] = coords

    uncached = {k: v for k, v in unique_coords.items() if k not in cache}

    print(f"Unique coordinates: {len(unique_coords)}")
    print(f"Already cached: {len(unique_coords) - len(uncached)}")
    print(f"Need to geocode: {len(uncached)}")

    if uncached:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        for i, (key, (lat, lng)) in enumerate(uncached.items()):
            addr = reverse_geocode(client, lat, lng)
            cache[key] = addr
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(uncached)} geocoded")
                save_cache(cache)
            time.sleep(1.1)
        client.close()
        save_cache(cache)
        print(f"Geocoded {len(uncached)} new coordinates")
    else:
        print("Cache is up to date")


if __name__ == "__main__":
    main()
