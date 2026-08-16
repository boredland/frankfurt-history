#!/usr/bin/env python3
"""One-shot migration: fold existing FFM data into the unified records format.

Inputs:
  data/stolpersteine-scraped/*.json   (frankfurt.de bios, one file per location)
  data/stolpersteine-ffm.json         (WFS location list, 793 entries)
  data/stolpersteine-records/frankfurt-am-main/*.json  (OSM stone records, already written)

Outputs:
  data/stolpersteine-records/frankfurt-am-main/*.json  (enriched + new location-records)

Strategy:
  1. Pass 1 — Attach scraped bios to existing OSM stone records by matching
     ``refs.website`` against the bio's ``source_url``. A single bio may cover
     multiple people, so it gets attached to every matching stone record.

  2. Pass 2 — For WFS entries whose address has no OSM coverage, create a
     location-level record (id slug = address slug, person.name = null) using
     WFS coords. Attach scraped bios that match the WFS URL.

  3. Pass 3 — For WFS entries with no URL and no OSM coverage, create a
     bare location-level record with just coords + address. These have no bio.

Run once; idempotent (preserves enricher state on rerun).
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _slug import slugify  # noqa: E402  (needs the sys.path line above)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCRAPED_DIR = DATA_DIR / "stolpersteine-scraped"
WFS_PATH = DATA_DIR / "stolpersteine-ffm.json"
RECORDS_DIR = DATA_DIR / "stolpersteine-records" / "frankfurt-am-main"


def log(msg: str) -> None:
    print(msg, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def addr_slug(street: str, house: str) -> str:
    return f"{slugify(street)}-{slugify(house)}".strip("-")


def normalize_bio(bio: dict) -> dict:
    """Convert old scraped-bio shape into the new bios entry shape."""
    return {
        "source": "frankfurt.de",
        "source_url": bio.get("source_url", ""),
        "lang": "de",
        "text": bio.get("text", ""),
        "text_en": bio.get("text_en") or None,
    }


def extract_names_from_bio_text(text: str) -> list[str]:
    """First non-empty line of a frankfurt.de bio is usually a comma-separated list
    of surnames + given names (e.g., 'Blumenthal, Meta und Fritz Günther')."""
    if not text:
        return []
    first = next((l.strip() for l in text.split("\n") if l.strip()), "")
    if not first or len(first) > 120:
        return []
    # Bios with sentence punctuation in line 1 are not name headers.
    if re.search(r"[.!?]", first):
        return []
    return [first]


def load_bios_by_source_url() -> dict[str, list[dict]]:
    """Index scraped bios by their frankfurt.de source URL.

    Same bio source URL may appear in multiple scraped files (rare, defensive)."""
    by_url: dict[str, list[dict]] = {}
    for f in SCRAPED_DIR.glob("*.json"):
        data = json.loads(f.read_text())
        for bio in data.get("biographies", []):
            url = bio.get("source_url")
            if not url:
                continue
            by_url.setdefault(url, []).append(bio)
    return by_url


def load_bios_by_location_url() -> dict[str, dict]:
    """Index full scraped-file payloads by their location URL (the file-level ``url``)."""
    by_url: dict[str, dict] = {}
    for f in SCRAPED_DIR.glob("*.json"):
        data = json.loads(f.read_text())
        url = data.get("url")
        if url:
            by_url[url] = data
    return by_url


def location_images_from_scraped(scraped: dict) -> list[dict]:
    """Extract location-level images (Stolperstein photos) from a scraped file."""
    images = []
    for url in scraped.get("location", {}).get("images", []):
        images.append({"url": url, "source": "frankfurt.de", "kind": "stone"})
    return images


def bio_images_from_scraped(bio: dict) -> list[dict]:
    images = []
    for url in bio.get("images") or []:
        images.append({"url": url, "source": "frankfurt.de", "kind": "biography"})
    return images


# ---------- Pass 1: attach bios to OSM stone records ----------

def pass1_attach_to_osm(bios_by_source_url: dict[str, list[dict]],
                        scraped_by_loc_url: dict[str, dict]) -> set[str]:
    """Returns the set of bio source_urls that were matched to OSM records."""
    matched_bio_urls: set[str] = set()
    osm_records_with_bios = 0

    for path in sorted(RECORDS_DIR.glob("*.json")):
        rec = json.loads(path.read_text())
        # Skip non-OSM records (shouldn't exist yet on first run, but defensive on rerun).
        if "osm" not in rec.get("enrichers", {}):
            continue
        website = rec["refs"].get("website")
        if not website:
            continue

        # The OSM website points to a frankfurt.de bio (familien/*) URL.
        bios = bios_by_source_url.get(website, [])
        if not bios:
            continue

        # Find scraped file for the LOCATION (standorte/*) — gives us location-level images.
        # The bio URL alone doesn't give us this; we need the scraped file that contained it.
        location_images: list[dict] = []
        for scraped in scraped_by_loc_url.values():
            for bio in scraped.get("biographies", []):
                if bio.get("source_url") == website:
                    location_images = location_images_from_scraped(scraped)
                    break
            if location_images:
                break

        rec["biographies"] = [normalize_bio(b) for b in bios]
        images: list[dict] = list(location_images)
        for bio in bios:
            images.extend(bio_images_from_scraped(bio))
        # De-dup by URL.
        seen: set[str] = set()
        rec["images"] = [im for im in images if not (im["url"] in seen or seen.add(im["url"]))]
        rec["enrichers"]["frankfurt_de"] = {"fetched_at": now_iso(), "found": True}

        path.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
        matched_bio_urls.add(website)
        osm_records_with_bios += 1

    log(f"  Pass 1: {osm_records_with_bios} OSM records got bios "
        f"({len(matched_bio_urls)} unique frankfurt.de URLs)")
    return matched_bio_urls


# ---------- Pass 2/3: create location records for WFS entries not covered ----------

def pass2_create_wfs_records(scraped_by_loc_url: dict[str, dict]) -> int:
    """Create location-level records for WFS entries with no OSM stone at that address."""
    # Index existing OSM record addresses.
    osm_addr_slugs: set[str] = set()
    for path in RECORDS_DIR.glob("*.json"):
        rec = json.loads(path.read_text())
        a = rec.get("address", {})
        if a.get("street") and a.get("house_number"):
            osm_addr_slugs.add(addr_slug(a["street"], a["house_number"]))

    wfs = json.loads(WFS_PATH.read_text())
    created = 0
    skipped = 0
    with_bios = 0

    for entry in wfs:
        street = entry.get("street", "")
        house = entry.get("house_number", "")
        if not (street and house):
            skipped += 1
            continue
        slug = addr_slug(street, house)
        if slug in osm_addr_slugs:
            # OSM already covers this address — bios attached in Pass 1.
            skipped += 1
            continue

        loc_url = entry.get("url")
        scraped = scraped_by_loc_url.get(loc_url) if loc_url else None
        bios = (scraped or {}).get("biographies", []) if scraped else []

        # Collect names from bio first lines for the commemorates list.
        commemorates: list[str] = []
        for b in bios:
            commemorates.extend(extract_names_from_bio_text(b.get("text", "")))

        record = {
            "id": f"frankfurt-am-main/{slug}",
            "city": "frankfurt-am-main",
            "city_name": "Frankfurt am Main",
            "country": "DE",
            "coords": [round(float(entry["lat"]), 7), round(float(entry["lng"]), 7)],
            "coords_source": "wfs",
            "person": {
                "name": None,
                "birth_date": None,
                "death_date": None,
                "birth_place": None,
                "death_place": None,
            },
            "address": {
                "street": street,
                "house_number": house,
                "postcode": entry.get("zip") or None,
                "district": None,
                "formatted": entry.get("address") or f"{street} {house}",
            },
            "commemorates": commemorates,
            "inscription": None,
            "laying_date": (scraped or {}).get("location", {}).get("laying_date") or None,
            "artist": None,
            "material": None,
            "refs": {
                "osm_id": None,
                "wfs_url": loc_url,
                "wikidata": None,
                "wikipedia": None,
                "wikimedia_commons": None,
                "image": None,
                "website": loc_url,
                "network": None,
            },
            "biographies": [normalize_bio(b) for b in bios],
            "images": [],
            "enrichers": {
                "wfs": {"fetched_at": now_iso()},
            },
        }

        # Images: location-level + bio-level, deduplicated.
        if scraped:
            imgs: list[dict] = location_images_from_scraped(scraped)
            for b in bios:
                imgs.extend(bio_images_from_scraped(b))
            seen: set[str] = set()
            record["images"] = [im for im in imgs if not (im["url"] in seen or seen.add(im["url"]))]
            record["enrichers"]["frankfurt_de"] = {"fetched_at": now_iso(), "found": True}

        if bios:
            with_bios += 1

        out_path = RECORDS_DIR / f"{slug}.json"
        if out_path.exists():
            log(f"  COLLISION: {slug}.json already exists — writing {slug}-2.json instead")
            candidate, n = slug, 2
            while (RECORDS_DIR / f"{candidate}.json").exists():
                candidate = f"{slug}-{n}"
                n += 1
            out_path = RECORDS_DIR / f"{candidate}.json"
            record["id"] = f"frankfurt-am-main/{candidate}"
        out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        created += 1

    log(f"  Pass 2: created {created} WFS-derived location records "
        f"({with_bios} with bios, {skipped} skipped — already in OSM or no addr)")
    return created


def main() -> int:
    if not RECORDS_DIR.exists():
        log(f"ERROR: {RECORDS_DIR} does not exist. Run fetch_osm_stolpersteine.py first.")
        return 1

    log("Loading scraped indices…")
    bios_by_source_url = load_bios_by_source_url()
    scraped_by_loc_url = load_bios_by_location_url()
    log(f"  {len(bios_by_source_url)} unique bio source URLs across "
        f"{sum(len(v) for v in bios_by_source_url.values())} bios in "
        f"{len(scraped_by_loc_url)} scraped files")

    log("Pass 1: attaching bios to OSM stone records…")
    pass1_attach_to_osm(bios_by_source_url, scraped_by_loc_url)

    log("Pass 2: creating records for WFS locations not in OSM…")
    pass2_create_wfs_records(scraped_by_loc_url)

    total = len(list(RECORDS_DIR.glob("*.json")))
    log(f"\nDone. {total} total records in {RECORDS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
