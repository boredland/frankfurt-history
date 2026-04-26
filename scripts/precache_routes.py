#!/usr/bin/env python3
"""Pre-cache walking routes between nearby POIs via OpenRouteService.

For each POI, finds the 3 nearest POIs within the same theme (haversine)
and fetches walking routes from ORS. Writes results to
app/public/data/routes/<theme>/<poi-slug>.json.

Only fetches routes that don't already exist (incremental).

Requires ORS_API_KEY env var.
"""

import json
import math
import os
import sys
import time
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "public" / "data"
ROUTES_DIR = DATA_DIR / "routes"
ORS_API_KEY = os.environ.get("ORS_API_KEY", "")
ORS_BASE = "https://api.openrouteservice.org/v2/directions/foot-walking"
NEIGHBORS = 3
REQUEST_DELAY = 1.6  # ~37 req/min, under ORS free tier limit of 40


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_pois(geojson_path: Path) -> list[dict]:
    data = json.loads(geojson_path.read_text())
    pois = []
    for f in data["features"]:
        coords = f["geometry"]["coordinates"]
        props = f["properties"]
        pois.append({
            "slug": props["slug"],
            "lng": coords[0],
            "lat": coords[1],
            "title": props.get("title", ""),
        })
    return pois


def nearest_neighbors(poi: dict, all_pois: list[dict], n: int) -> list[dict]:
    distances = []
    for other in all_pois:
        if other["slug"] == poi["slug"]:
            continue
        d = haversine(poi["lat"], poi["lng"], other["lat"], other["lng"])
        distances.append((d, other))
    distances.sort(key=lambda x: x[0])
    return [{"distance_m": round(d, 1), **o} for d, o in distances[:n]]


def fetch_route(start_lng: float, start_lat: float, end_lng: float, end_lat: float) -> dict | None:
    if not ORS_API_KEY:
        return None
    try:
        r = httpx.get(
            ORS_BASE,
            params={"start": f"{start_lng},{start_lat}", "end": f"{end_lng},{end_lat}"},
            headers={"Authorization": ORS_API_KEY},
            timeout=15,
        )
        if r.status_code != 200:
            print(f"    ORS error {r.status_code}: {r.text[:200]}")
            return None
        data = r.json()
        feat = data["features"][0]
        props = feat["properties"]["summary"]
        return {
            "geometry": feat["geometry"],
            "distance_m": round(props["distance"], 1),
            "duration_s": round(props["duration"], 1),
            "steps": [
                {
                    "instruction": step["instruction"],
                    "distance_m": round(step["distance"], 1),
                    "duration_s": round(step["duration"], 1),
                }
                for step in feat["properties"].get("segments", [{}])[0].get("steps", [])
            ],
        }
    except Exception as e:
        print(f"    ORS fetch error: {e}")
        return None


def main():
    if not ORS_API_KEY:
        print("ORS_API_KEY not set — generating haversine-only routes (no geometry/steps)")

    geojson_files = sorted(DATA_DIR.glob("*.geojson"))
    if not geojson_files:
        print("No GeoJSON files found in", DATA_DIR)
        sys.exit(1)

    total_fetched = 0
    total_cached = 0

    for gj_path in geojson_files:
        theme = gj_path.stem
        pois = load_pois(gj_path)
        if not pois:
            continue

        theme_dir = ROUTES_DIR / theme
        theme_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n{theme}: {len(pois)} POIs")

        for poi in pois:
            out_path = theme_dir / f"{poi['slug']}.json"
            if out_path.exists():
                total_cached += 1
                continue

            neighbors = nearest_neighbors(poi, pois, NEIGHBORS)
            routes = []

            for nb in neighbors:
                route_data = {
                    "target_slug": nb["slug"],
                    "target_title": nb["title"],
                    "straight_distance_m": nb["distance_m"],
                }

                if ORS_API_KEY:
                    route = fetch_route(poi["lng"], poi["lat"], nb["lng"], nb["lat"])
                    if route:
                        route_data.update(route)
                        total_fetched += 1
                        time.sleep(REQUEST_DELAY)
                    else:
                        route_data["distance_m"] = nb["distance_m"]
                        route_data["duration_s"] = round(nb["distance_m"] / 1.3, 1)
                else:
                    route_data["distance_m"] = nb["distance_m"]
                    route_data["duration_s"] = round(nb["distance_m"] / 1.3, 1)

                routes.append(route_data)

            out_path.write_text(json.dumps(routes, ensure_ascii=False) + "\n")
            print(f"  {poi['slug']}: {len(routes)} routes")

    print(f"\nDone. {total_fetched} routes fetched, {total_cached} already cached.")


if __name__ == "__main__":
    main()
