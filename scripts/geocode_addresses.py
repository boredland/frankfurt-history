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


def reverse_geocode(client: httpx.Client, lat: float, lng: float, subtitle: str) -> str:
    try:
        r = client.get(PHOTON_REVERSE, params={"lat": lat, "lon": lng})
        r.raise_for_status()
        data = r.json()
        features = data.get("features", [])
        if features:
            addr = format_addr(features[0].get("properties", {}))
            if addr:
                return addr

        # Fallback: forward geocode the subtitle if it looks like an address
        if subtitle and STREET_RE.search(subtitle):
            time.sleep(0.15)
            r2 = client.get(
                PHOTON_FORWARD,
                params={
                    "q": f"{subtitle}, Frankfurt am Main",
                    "lat": lat,
                    "lon": lng,
                    "limit": 1,
                },
            )
            r2.raise_for_status()
            data2 = r2.json()
            features2 = data2.get("features", [])
            if features2:
                addr2 = format_addr(features2[0].get("properties", {}))
                if addr2:
                    return addr2

        return ""
    except Exception as e:
        print(f"  Error geocoding {lat},{lng}: {e}", flush=True)
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

    print(f"Unique coordinates: {len(unique_coords)}", flush=True)
    print(f"Already cached: {len(unique_coords) - len(uncached)}", flush=True)
    print(f"Need to geocode: {len(uncached)}", flush=True)

    if not uncached:
        print("Cache is up to date", flush=True)
        return

    eta_min = len(uncached) * 0.3 / 60
    print(f"Estimated time: {eta_min:.0f} minutes", flush=True)

    client = httpx.Client(timeout=15)
    for i, (key, (lat, lng, subtitle)) in enumerate(uncached.items()):
        addr = reverse_geocode(client, lat, lng, subtitle)
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
