#!/usr/bin/env python3
"""Convert scraped Stolpersteine JSONs into markdown articles for the app.

Creates one article per biography in data/stolpersteine/ as a new theme.
Coordinates come from WFS (if available) or geocoding via Photon.
The crawler data is authoritative for content; WFS only supplies coordinates.

Usage:
    uv run scripts/build_stolpersteine.py
"""

import json
import re
import time
import urllib.parse
import unicodedata
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCRAPED_DIR = DATA_DIR / "stolpersteine-scraped"
WFS_PATH = DATA_DIR / "stolpersteine-ffm.json"
COORD_CACHE_PATH = DATA_DIR / "stolpersteine-coords.json"
THEME_DIR = DATA_DIR / "stolpersteine"
RECORDS_DIR = DATA_DIR / "stolpersteine-records" / "frankfurt-am-main"

UA = "FrankfurtHistoryApp/1.0 (https://history.jonas-strassel.de)"


def geocode_address(address: str) -> tuple[float, float] | None:
    """Geocode a Frankfurt address via Photon."""
    query = f"{address}, Frankfurt am Main"
    params = urllib.parse.urlencode({
        "q": query,
        "lat": 50.11,
        "lon": 8.68,
        "limit": 1,
    })
    req = urllib.request.Request(
        f"https://photon.komoot.io/api?{params}",
        headers={"User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        features = data.get("features", [])
        if features:
            coords = features[0]["geometry"]["coordinates"]
            lat, lng = coords[1], coords[0]
            if 49.9 < lat < 50.3 and 8.3 < lng < 9.0:
                return round(lat, 7), round(lng, 7)
    except Exception as e:
        print(f"  Geocode failed for {address}: {e}")
    return None


def slugify(text: str) -> str:
    s = text.lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def extract_person_name(bio_text: str) -> str:
    """Extract person name from the first line(s) of bio text."""
    lines = [l.strip() for l in bio_text.split("\n") if l.strip()]
    if lines:
        name = lines[0]
        if len(name) < 100 and "," in name:
            return name
        if len(name) < 60:
            return name
    return ""


STOP_MARKERS = {
    "Geburtsdatum:", "Geburtsdaten:", "Geburtsdatum", "Sterbedatum:",
    "teilen", "tweet", "mitteilen", "mail",
    "Initiative Stolpersteine", "Stolperstein Standort", "Standort Stolpersteine",
}

# Lines like "Stolperstein <street> <name>" that appear before the share buttons.
_CAPTION_PREFIX = re.compile(r"^Stolperstein(e)?\b")


def clean_bio_text(bio_text: str, person_name: str) -> tuple[str, dict[str, str]]:
    """Trim share/nav cruft and pull birth/deport/death meta from the tail.

    Returns (clean_text, meta) where meta has keys 'birth', 'deportation', 'death'
    when found.
    """
    paragraphs = [p.strip() for p in bio_text.split("\n\n") if p.strip()]

    # Drop leading title duplicates (e.g. first line == person_name)
    while paragraphs and paragraphs[0] in {person_name, person_name.replace(",", "")}:
        paragraphs.pop(0)
    # Drop a leading short image-caption-ish line (no sentence punctuation, < 60 chars)
    if paragraphs and len(paragraphs[0]) < 60 and not re.search(r"[.!?]", paragraphs[0]):
        paragraphs.pop(0)

    cut = len(paragraphs)
    for i, p in enumerate(paragraphs):
        if p in STOP_MARKERS or any(p.startswith(m) for m in ("Geburtsdatum", "Sterbedatum")):
            cut = i
            break

    body_paragraphs = paragraphs[:cut]
    tail = paragraphs[cut:]

    meta: dict[str, str] = {}
    labels = {"Geburtsdatum:": "birth", "Deportation:": "deportation", "Todesdatum:": "death"}
    pending: list[str] = []
    values: list[str] = []
    for p in tail:
        if p in labels:
            pending.append(labels[p])
        elif pending and p not in STOP_MARKERS and not _CAPTION_PREFIX.match(p):
            if re.match(r"\d", p) or "deportiert" in p.lower() or "auschwitz" in p.lower():
                values.append(p)
    for key, val in zip(pending, values):
        meta[key] = val

    last_name = person_name.split(",")[0].strip() if "," in person_name else person_name
    abbrev_re = re.compile(r"\b(?:geb|geboren|verh|verstorben|Dr|Prof|St|Jr|Sr|Nr|jr)\.")

    def is_caption_like(s: str) -> bool:
        if len(s) >= 100:
            return False
        stripped = abbrev_re.sub("", s)
        return not re.search(r"[.!?](?:\s|$)", stripped)

    while body_paragraphs:
        last = body_paragraphs[-1]
        if not is_caption_like(last):
            break
        if _CAPTION_PREFIX.match(last) or (last_name and last_name in last):
            body_paragraphs.pop()
            continue
        break

    return "\n\n".join(body_paragraphs), meta


def build_markdown(person_name: str, address: str, laying_date: str,
                   bio_text: str, bio_images: list[str],
                   location_images: list[str], source_url: str,
                   lat: float, lng: float, poi_id: int) -> str:
    lines = [
        "---",
        f"id: {poi_id}",
        f'title: "Stolperstein — {person_name}"',
        f'subtitle: "{address}"',
        f"coordinates: [{lat}, {lng}]",
    ]
    if laying_date:
        lines.append(f'updated_at: "{laying_date}"')
    lines += [
        "filters:",
        '  - "Stolpersteine"',
        "---",
        "",
        f"# Stolperstein — {person_name}",
        "",
        f"*{address}*",
        "",
    ]

    if location_images:
        lines.append(f"![Stolperstein {person_name}]({location_images[0]})")
        lines.append("")

    clean_bio, _ = clean_bio_text(bio_text, person_name)
    if clean_bio:
        lines.append(clean_bio)
        lines.append("")

    if bio_images:
        lines.append("## Gallery")
        lines.append("")
        lines.append("<!-- gallery:standard -->")
        for img in bio_images:
            lines.append(f"![{person_name}]({img})")
        lines.append("")

    if source_url:
        lines.append("## Links")
        lines.append("")
        lines.append(f"- [frankfurt.de]({source_url})")
        lines.append("")

    if laying_date:
        lines.append(f"*Steinverlegung am: {laying_date}*")
        lines.append("")

    return "\n".join(lines)


def normalize_address(address: str) -> str:
    """Collapse spelling variants so record and scrape addresses compare equal.

    Records come from OSM and the Initiative list, articles from frankfurt.de:
    the same stone appears as "Bolongarostr. 128" / "Bolongarostraße 128" and
    "Alt Heddernheim 33" / "Alt-Heddernheim 33".
    """
    s = (address or "").lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # Expand the "str." abbreviation while the period is still there; it may be
    # glued to the street name ("Radilostr.") so no leading word boundary holds.
    s = re.sub(r"str\.", "strasse", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"\bstr\b", "strasse", s)
    return s.replace(" ", "")


def tidy_address(address: str) -> str:
    """Expand the "str." abbreviation for display and drop a stray period.

    Record addresses come from mixed sources: "Radilostr. 29" and the
    misspelled "Hostatostaße. 3" both occur.
    """
    s = re.sub(r"str\.(?=\s|$)", "straße", (address or "").strip())
    s = re.sub(r"(?<=[a-zäöüß])\.(?=\s\d)", "", s)
    return re.sub(r"\s+", " ", s).strip()


def built_addresses() -> set[str]:
    """Normalised addresses that already have at least one article."""
    out = set()
    for md in THEME_DIR.glob("*.md"):
        if md.stem == "_index":
            continue
        m = re.search(r'^subtitle:\s*"([^"]*)"', md.read_text(), re.M)
        if m:
            out.add(normalize_address(m.group(1)))
    return out


def record_groups() -> dict[str, list[dict]]:
    """Group biography-bearing records by normalised address."""
    groups: dict[str, list[dict]] = {}
    if not RECORDS_DIR.is_dir():
        return groups
    for path in sorted(RECORDS_DIR.glob("*.json")):
        try:
            rec = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if not any(b.get("text") for b in (rec.get("biographies") or [])):
            continue
        if not rec.get("coords"):
            continue
        key = normalize_address((rec.get("address") or {}).get("formatted"))
        if key:
            groups.setdefault(key, []).append(rec)
    return groups


def record_person_names(records: list[dict]) -> str:
    """Render "Surname, Given und Given" for the people sharing one address.

    Location-level records have no `person.name`; they list their victims in
    `commemorates`, already in "Surname, Given" form.
    """
    commemorated: list[str] = []
    for rec in records:
        if (rec.get("person") or {}).get("name"):
            continue
        for entry in rec.get("commemorates") or []:
            entry = (entry or "").strip()
            if entry and entry not in commemorated:
                commemorated.append(entry)

    by_surname: dict[str, list[str]] = {}
    order: list[str] = []
    for rec in records:
        name = ((rec.get("person") or {}).get("name") or "").strip()
        if not name:
            continue
        parts = name.split()
        surname, given = parts[-1], " ".join(parts[:-1])
        if surname not in by_surname:
            by_surname[surname] = []
            order.append(surname)
        if given and given not in by_surname[surname]:
            by_surname[surname].append(given)
    chunks = []
    for surname in order:
        givens = by_surname[surname]
        if not givens:
            chunks.append(surname)
        elif len(givens) == 1:
            chunks.append(f"{surname}, {givens[0]}")
        else:
            chunks.append(f"{surname}, {', '.join(givens[:-1])} und {givens[-1]}")
    return "; ".join(chunks or commemorated)


def load_coord_cache() -> dict[str, tuple[float, float]]:
    """Load coordinate cache: address → (lat, lng). Seeded from WFS."""
    cache: dict[str, tuple[float, float]] = {}
    if COORD_CACHE_PATH.exists():
        for addr, coords in json.loads(COORD_CACHE_PATH.read_text()).items():
            cache[addr] = (coords[0], coords[1])
    if WFS_PATH.exists():
        for s in json.loads(WFS_PATH.read_text()):
            addr = s.get("address", "")
            if addr and s.get("lat") and s.get("lng"):
                cache[addr] = (s["lat"], s["lng"])
    return cache


def save_coord_cache(cache: dict[str, tuple[float, float]]):
    out = {addr: list(coords) for addr, coords in sorted(cache.items())}
    COORD_CACHE_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")


def resolve_coords(address: str, cache: dict[str, tuple[float, float]]) -> tuple[float, float] | None:
    if address in cache:
        return cache[address]
    result = geocode_address(address)
    if result:
        cache[address] = result
        time.sleep(1)
    return result


def main():
    THEME_DIR.mkdir(exist_ok=True)
    coord_cache = load_coord_cache()

    existing_ids = set()
    existing_keys: dict[tuple[str, str], Path] = {}
    for f in THEME_DIR.glob("*.md"):
        if f.stem == "_index":
            continue
        m = re.match(r"(\d+)-(.+)$", f.stem)
        if not m:
            continue
        existing_ids.add(int(m.group(1)))
        slug = m.group(2)
        sub_match = re.search(r'^subtitle:\s*"([^"]*)"', f.read_text(), re.M)
        address_key = sub_match.group(1) if sub_match else ""
        existing_keys[(address_key, slug)] = f
    poi_id = max(existing_ids, default=10000)

    created = 0
    skipped = 0
    geocoded = 0

    for scraped_file in sorted(SCRAPED_DIR.glob("*.json")):
        data = json.loads(scraped_file.read_text())
        address = data.get("address", scraped_file.stem)
        laying_date = data.get("location", {}).get("laying_date", "")
        location_images = data.get("location", {}).get("images", [])
        source_url = data.get("url", "")

        coords = resolve_coords(address, coord_cache)
        if not coords:
            print(f"  SKIP {address} — no coordinates")
            skipped += 1
            continue

        lat, lng = coords
        if address not in coord_cache or coord_cache[address] != coords:
            geocoded += 1
            print(f"  Geocoded {address} → [{lat}, {lng}]")

        for bio in data.get("biographies", []):
            if not bio.get("text"):
                continue

            person_name = extract_person_name(bio["text"])
            if not person_name:
                person_name = address

            bio_slug = slugify(person_name)
            if (address, bio_slug) in existing_keys:
                continue

            poi_id += 1
            md_name = f"{poi_id}-{bio_slug}.md"
            md = build_markdown(
                person_name=person_name,
                address=address,
                laying_date=laying_date,
                bio_text=bio["text"],
                bio_images=bio.get("images", []),
                location_images=location_images,
                source_url=bio.get("source_url", source_url),
                lat=lat,
                lng=lng,
                poi_id=poi_id,
            )
            (THEME_DIR / md_name).write_text(md)
            created += 1

    # Backfill from records: stones the frankfurt.de crawl never produced a page
    # for, but whose biography the Initiative/OSM enrichers did find. Without
    # this they exist only as JSON nothing reads.
    backfilled = 0
    already = built_addresses()
    for key, records in sorted(record_groups().items()):
        if key in already:
            continue
        records.sort(key=lambda r: (r.get("person") or {}).get("name") or "")
        head = records[0]
        address = tidy_address((head.get("address") or {}).get("formatted") or key)
        person_name = record_person_names(records) or address
        bio = max(
            (b for r in records for b in (r.get("biographies") or []) if b.get("text")),
            key=lambda b: len(b["text"]),
        )
        images = [
            img["url"]
            for r in records
            for img in (r.get("images") or [])
            if img.get("url")
        ]
        lat, lng = head["coords"]

        poi_id += 1
        md = build_markdown(
            person_name=person_name,
            address=address,
            laying_date=head.get("laying_date") or "",
            bio_text=bio["text"],
            bio_images=images[1:],
            location_images=images[:1],
            source_url=bio.get("source_url") or (head.get("refs") or {}).get("website", ""),
            lat=lat,
            lng=lng,
            poi_id=poi_id,
        )
        (THEME_DIR / f"{poi_id}-{slugify(person_name)}.md").write_text(md)
        already.add(key)
        backfilled += 1

    # Write theme index
    (THEME_DIR / "_index.md").write_text("""---
id: 7
title: "Stolpersteine"
short_title: "Stolpersteine"
---

# Stolpersteine
""")

    save_coord_cache(coord_cache)

    print(f"\nCreated: {created} articles")
    print(f"Backfilled from records: {backfilled} articles")
    print(f"Skipped: {skipped} (no coordinates)")
    print(f"Geocoded: {geocoded} new addresses")
    print(f"Total: {len(list(THEME_DIR.glob('*.md'))) - 1} articles in {THEME_DIR}")
    print(f"Coord cache: {len(coord_cache)} entries")


if __name__ == "__main__":
    main()
