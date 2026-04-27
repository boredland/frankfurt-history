#!/usr/bin/env python3
"""Reverse geocode POI coordinates to street addresses via Photon (Komoot).

Reads coordinates from data/de/<theme>/*.md frontmatter, reverse geocodes
each unique coordinate pair, and caches results in data/addresses.json.
Only calls the API for coordinates not already cached.

Uses Photon (https://photon.komoot.io) — better precision than Nominatim,
no API key required, same OSM data source.
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
PHOTON_URL = "https://photon.komoot.io/reverse"


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
        r = client.get(PHOTON_URL, params={"lat": lat, "lon": lng})
        r.raise_for_status()
        data = r.json()
        features = data.get("features", [])
        if not features:
            return ""
        props = features[0].get("properties", {})
        street = props.get("street", "")
        house = props.get("housenumber", "")
        if street and house:
            return f"{street} {house}"
        return street or ""
    except Exception as e:
        print(f"  Error geocoding {lat},{lng}: {e}", flush=True)
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

    print(f"Unique coordinates: {len(unique_coords)}", flush=True)
    print(f"Already cached: {len(unique_coords) - len(uncached)}", flush=True)
    print(f"Need to geocode: {len(uncached)}", flush=True)

    if not uncached:
        print("Cache is up to date", flush=True)
        return

    eta_min = len(uncached) * 0.3 / 60
    print(f"Estimated time: {eta_min:.0f} minutes", flush=True)

    client = httpx.Client(timeout=15)
    for i, (key, (lat, lng)) in enumerate(uncached.items()):
        addr = reverse_geocode(client, lat, lng)
        cache[key] = addr
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(uncached)} geocoded", flush=True)
            save_cache(cache)
        time.sleep(0.25)
    client.close()
    save_cache(cache)
    print(f"Geocoded {len(uncached)} new coordinates", flush=True)


if __name__ == "__main__":
    main()
