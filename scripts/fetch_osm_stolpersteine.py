#!/usr/bin/env python3
"""Fetch Stolpersteine from OpenStreetMap via Overpass, split per city.

Pulls every node tagged ``memorial=stolperstein`` (or ``memorial:type=stolperstein``)
globally, normalises tags into the unified per-stone record schema, and writes
one JSON per stone under ``data/stolpersteine-records/<city-slug>/<stone-slug>.json``.

Usage:
    uv run scripts/fetch_osm_stolpersteine.py                     # default: frankfurt-am-main, berlin
    uv run scripts/fetch_osm_stolpersteine.py --city berlin       # one city
    uv run scripts/fetch_osm_stolpersteine.py --city berlin hamburg
    uv run scripts/fetch_osm_stolpersteine.py --all               # every city OSM knows about

Record schema (see also: data/stolpersteine-records/README.md eventually):

    {
      "id":            "<city-slug>/<stone-slug>",
      "city":          "frankfurt-am-main",
      "city_name":     "Frankfurt am Main",
      "country":       "DE",
      "coords":        [lat, lng],
      "coords_source": "osm",

      "person": {
        "name":        "Adolf Moritz Steinschneider",
        "birth_date":  "1933",
        "death_date":  "1944",
        "birth_place": null,
        "death_place": null
      },

      "address": {
        "street":       "Untermainkai",
        "house_number": "20",
        "postcode":     null,
        "district":     "Bahnhofsviertel",
        "formatted":    "Untermainkai 20"
      },

      "inscription":  "Hier wohnte ...",
      "laying_date":  "2004-10-15",
      "artist":       null,
      "material":     null,

      "refs": {
        "osm_id":            745068251,
        "osm_version":       7,
        "wikidata":          null,
        "wikipedia":         "de:Liste der Stolpersteine in ...",
        "wikimedia_commons": null,
        "image":             "File:Stolperstein-ffm-...jpg",
        "website":           "https://frankfurt.de/..."
      },

      "biographies": [],   # enricher-populated, see initiative scrapers
      "images":      [],   # enricher-populated
      "enrichers":   {"osm": {"fetched_at": "..."}}
    }
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECORDS_DIR = DATA_DIR / "stolpersteine-records"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
UA = "FrankfurtHistoryBot/1.0 (https://history.jonas-strassel.de)"

OVERPASS_QUERY = """[out:json][timeout:300];
(
  node["memorial:type"="stolperstein"];
  node["memorial"="stolperstein"];
);
out tags center 60000;
"""

_start_time = time.monotonic()


def log(msg: str) -> None:
    elapsed = time.monotonic() - _start_time
    m, s = divmod(int(elapsed), 60)
    print(f"[{m:02d}:{s:02d}] {msg}", flush=True)


# ---------- City name normalisation ----------

# Hand-curated map of common variant city names → canonical name.
# OSM contributors are inconsistent ("Frankfurt am Main" vs "Frankfurt a.M.") and
# we want one directory per city.
CITY_CANON = {
    "frankfurt a.m.": "Frankfurt am Main",
    "frankfurt a. m.": "Frankfurt am Main",
    "frankfurt a.m": "Frankfurt am Main",
    "frankfurt am main": "Frankfurt am Main",
    "offenbach a.m.": "Offenbach am Main",
    "offenbach a. m.": "Offenbach am Main",
    "offenbach am main": "Offenbach am Main",
    "münchen": "München",
    "muenchen": "München",
    "köln": "Köln",
    "koeln": "Köln",
    "düsseldorf": "Düsseldorf",
    "duesseldorf": "Düsseldorf",
    "würzburg": "Würzburg",
    "wuerzburg": "Würzburg",
    "nürnberg": "Nürnberg",
    "nuernberg": "Nürnberg",
}


def canonical_city(raw: str) -> str:
    cleaned = raw.strip()
    # Strip leading postcodes like "76530 Baden-Baden"
    m = re.match(r"^\d{4,5}\s+(.+)$", cleaned)
    if m:
        cleaned = m.group(1).strip()
    return CITY_CANON.get(cleaned.lower(), cleaned)


def slugify(text: str) -> str:
    """ASCII kebab-case slug. Folds German umlauts to digraphs."""
    s = text.lower()
    s = (s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
          .replace("á", "a").replace("à", "a").replace("â", "a")
          .replace("é", "e").replace("è", "e").replace("ê", "e")
          .replace("ó", "o").replace("ô", "o")
          .replace("í", "i").replace("ï", "i")
          .replace("ú", "u").replace("ç", "c").replace("ñ", "n"))
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


# ---------- Address extraction ----------

def parse_memorial_addr(raw: str) -> dict:
    """Parse ``memorial:addr`` like 'Untermainkai 20, Frankfurt a.M., Bahnhofsviertel, DE'."""
    parts = [p.strip() for p in raw.split(",")]
    out: dict = {"street": "", "house_number": "", "district": "", "country": "", "city": ""}
    if not parts:
        return out
    # First part: street + house number
    m = re.match(r"^(.*?)\s+(\d+\w?(?:\s*[-–/]\s*\d+\w?)?)$", parts[0])
    if m:
        out["street"], out["house_number"] = m.group(1).strip(), m.group(2).strip()
    else:
        out["street"] = parts[0]
    if len(parts) >= 2:
        out["city"] = parts[1]
    if len(parts) >= 3:
        out["district"] = parts[2]
    if len(parts) >= 4:
        out["country"] = parts[3]
    return out


def extract_address(tags: dict) -> tuple[dict, str]:
    """Return (address_dict, city_raw). Prefers explicit object:* tags, falls back to memorial:addr."""
    city_raw = tags.get("object:city", "").strip()
    street = tags.get("object:street", "").strip()
    house = tags.get("object:housenumber", "").strip()
    postcode = tags.get("object:postcode", "").strip()
    district = tags.get("object:suburb", "").strip()
    country = tags.get("object:country", "").strip()

    if not (city_raw and street):
        mem_addr = tags.get("memorial:addr", "")
        if mem_addr:
            parsed = parse_memorial_addr(mem_addr)
            city_raw = city_raw or parsed["city"]
            street = street or parsed["street"]
            house = house or parsed["house_number"]
            district = district or parsed["district"]
            country = country or parsed["country"]

    formatted = " ".join(x for x in (street, house) if x)
    return {
        "street": street,
        "house_number": house,
        "postcode": postcode or None,
        "district": district or None,
        "formatted": formatted,
    }, city_raw


# ---------- Stone slug ----------

def stone_slug(person_name: str, address: dict, osm_id: int) -> str:
    parts: list[str] = []
    if address.get("street"):
        parts.append(slugify(address["street"]))
    if address.get("house_number"):
        parts.append(slugify(address["house_number"]))
    if person_name:
        parts.append(slugify(person_name))
    slug = "-".join(p for p in parts if p)
    if not slug:
        slug = f"osm-{osm_id}"
    # Bound length to keep filenames sane.
    if len(slug) > 120:
        slug = slug[:120].rstrip("-")
    return slug


# ---------- Normalisation ----------

def normalize_node(node: dict) -> dict | None:
    tags = node.get("tags", {})
    if not tags:
        return None

    lat = node.get("lat")
    lng = node.get("lon")
    if lat is None or lng is None:
        # Some nodes return geometry under "center" when out is `center`.
        center = node.get("center", {})
        lat, lng = center.get("lat"), center.get("lon")
    if lat is None or lng is None:
        return None

    address, city_raw = extract_address(tags)
    if not city_raw:
        return None  # un-citified stones go in a separate bucket; handled by caller

    city_name = canonical_city(city_raw)
    person_name = tags.get("name", "").strip()
    osm_id = node["id"]
    slug = stone_slug(person_name, address, osm_id)

    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    return {
        "id": f"{slugify(city_name)}/{slug}",
        "city": slugify(city_name),
        "city_name": city_name,
        "country": tags.get("object:country", "").strip() or None,

        "coords": [round(float(lat), 7), round(float(lng), 7)],
        "coords_source": "osm",

        "person": {
            "name": person_name or None,
            "birth_date": tags.get("person:date_of_birth") or None,
            "death_date": tags.get("person:date_of_death") or None,
            "birth_place": tags.get("person:place_of_birth") or None,
            "death_place": tags.get("person:place_of_death") or None,
        },

        "address": address,

        "inscription": tags.get("inscription") or None,
        "laying_date": tags.get("start_date") or None,
        "artist": tags.get("artist_name") or None,
        "material": tags.get("material") or tags.get("material:de") or None,

        "refs": {
            "osm_id": osm_id,
            "osm_version": node.get("version"),
            "wikidata": tags.get("wikidata") or None,
            "wikipedia": tags.get("related:wikipedia") or tags.get("wikipedia") or None,
            "wikimedia_commons": tags.get("wikimedia_commons") or None,
            "image": tags.get("image") or None,
            "website": tags.get("website") or None,
            "network": tags.get("network") or None,
        },

        "biographies": [],
        "images": [],
        "enrichers": {"osm": {"fetched_at": fetched_at}},
    }


# ---------- Overpass ----------

def fetch_overpass() -> list[dict]:
    log("Querying Overpass for all stolpersteine globally…")
    data = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=420) as resp:
        body = resp.read()
    log(f"  Overpass response: {resp.status}, {len(body) / 1024 / 1024:.1f} MiB")
    return json.loads(body).get("elements", [])


# ---------- Writer ----------

def merge_into_existing(new: dict, path: Path) -> dict:
    """If a record already exists, preserve enricher-added fields (biographies, images, custom refs)."""
    if not path.exists():
        return new
    try:
        old = json.loads(path.read_text())
    except json.JSONDecodeError:
        return new
    # Preserve enrichment that OSM doesn't carry.
    if old.get("biographies"):
        new["biographies"] = old["biographies"]
    if old.get("images"):
        new["images"] = old["images"]
    # Preserve enricher provenance other than osm.
    for key, val in (old.get("enrichers") or {}).items():
        if key != "osm":
            new["enrichers"][key] = val
    # Preserve coords if OSM doesn't provide better than what we had.
    if old.get("coords_source") in {"wfs", "geocoded"} and old.get("coords") and not new.get("coords"):
        new["coords"] = old["coords"]
        new["coords_source"] = old["coords_source"]
    return new


def write_record(record: dict) -> Path:
    city_slug = record["city"]
    stone_slug_str = record["id"].split("/", 1)[1]
    out_dir = RECORDS_DIR / city_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stone_slug_str}.json"
    merged = merge_into_existing(record, path)
    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
    return path


# ---------- Main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", nargs="+", default=None,
                    help="City slug(s) to write (e.g. frankfurt-am-main berlin). Default: frankfurt-am-main berlin.")
    ap.add_argument("--all", action="store_true", help="Write records for every city OSM knows about.")
    ap.add_argument("--dry-run", action="store_true", help="Don't write files; just print counts per city.")
    args = ap.parse_args()

    if args.all:
        wanted: set[str] | None = None
    else:
        wanted = set(args.city) if args.city else {"frankfurt-am-main", "berlin"}

    elements = fetch_overpass()
    log(f"  {len(elements)} raw nodes")

    by_city: dict[str, list[dict]] = {}
    skipped_no_city = 0
    skipped_no_coords = 0
    for node in elements:
        if not node.get("tags"):
            continue
        if node.get("lat") is None and not node.get("center"):
            skipped_no_coords += 1
            continue
        if not (node["tags"].get("object:city") or node["tags"].get("memorial:addr")):
            skipped_no_city += 1
            continue
        rec = normalize_node(node)
        if rec is None:
            continue
        by_city.setdefault(rec["city"], []).append(rec)

    log(f"  Normalised {sum(len(v) for v in by_city.values())} stones across {len(by_city)} cities")
    log(f"  Skipped: {skipped_no_city} no-city, {skipped_no_coords} no-coords")

    if args.dry_run:
        for city, recs in sorted(by_city.items(), key=lambda kv: -len(kv[1])):
            marker = "*" if (wanted is None or city in wanted) else " "
            log(f"  {marker} {len(recs):>5}  {city}")
        return 0

    written = 0
    cities_written = 0
    for city, recs in by_city.items():
        if wanted is not None and city not in wanted:
            continue
        for rec in recs:
            write_record(rec)
            written += 1
        cities_written += 1
        log(f"  wrote {len(recs):>5} records → {city}/")

    log(f"Done. {written} records written across {cities_written} cities.")
    if wanted is not None:
        missing = wanted - set(by_city.keys())
        if missing:
            log(f"  WARNING: no OSM data for requested cities: {sorted(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
