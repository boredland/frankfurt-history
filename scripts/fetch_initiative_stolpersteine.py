#!/usr/bin/env python3
"""Backfill Stolpersteine records from the Initiative Stolpersteine Frankfurt
"Gesamtliste" PDF — the authoritative per-victim roster for Frankfurt am Main.

The city portal (frankfurt.de) only documents stones laid up to end of 2023, so
OSM + the frankfurt.de enricher together miss the ~500 victims of 2024+ layings.
The Initiative publishes a complete list of every stone ever laid (refreshed
every few months) as a sortable PDF. This script parses the "sorted by victim
name" edition and folds it into the unified record store, matching the schema
written by ``fetch_osm_stolpersteine.py``.

For each victim row it either:
  * enriches the matching existing record (fills empty birth/death/laying dates,
    district, persecution fate, victim group), preserving OSM coords and any
    frankfurt.de biographies/images, or
  * creates a new record (the 2024+ layings and anyone OSM never carried),
    resolving coordinates from the address cache (existing records +
    ``stolpersteine-coords.json``) where a sibling stone shares the address.

Stolperschwellen and Kopfsteine (collective threshold/marker stones) are written
as ``marker_type``-tagged records rather than individual victims.

Usage:
    uv run scripts/fetch_initiative_stolpersteine.py                # discover + download latest PDF
    uv run scripts/fetch_initiative_stolpersteine.py --pdf list.pdf # parse a local PDF
    uv run scripts/fetch_initiative_stolpersteine.py --dry-run      # parse + match, write nothing
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECORDS_DIR = DATA_DIR / "stolpersteine-records"
COORD_CACHE_PATH = DATA_DIR / "stolpersteine-coords.json"

CITY_SLUG = "frankfurt-am-main"
CITY_NAME = "Frankfurt am Main"
SOURCE_HOST = "stolpersteine-frankfurt.de"
SOURCE_KEY = "stolpersteine_frankfurt_de"

DOC_URL = "https://www.stolpersteine-frankfurt.de/de/dokumentation"
PDF_LINK_RE = re.compile(r'href="([^"]*gesamtliste_nach_namen[^"]*\.pdf)"')
STAND_RE = re.compile(r"stand[_-](\d{4}-\d{2}-\d{2})")
UA = "FrankfurtHistoryBot/1.0 (https://history.jonas-strassel.de)"

# Column order of the "nach den Namen der Opfer sortiert" table.
COLS = ["name", "birth_name", "birth_date", "address", "district", "fate", "death_date", "laying_date"]

# Name-cell title tokens dropped from the match key (kept in the display name).
TITLE_TOKENS = {"dr", "prof", "jun", "sen", "sr", "jr"}

_start = time.monotonic()


def log(msg: str) -> None:
    m, s = divmod(int(time.monotonic() - _start), 60)
    print(f"[{m:02d}:{s:02d}] {msg}", flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(text: str) -> str:
    """ASCII kebab-case slug. Folds German umlauts to digraphs."""
    s = (text or "").lower()
    s = (s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
          .replace("á", "a").replace("à", "a").replace("â", "a")
          .replace("é", "e").replace("è", "e").replace("ê", "e")
          .replace("ó", "o").replace("ô", "o")
          .replace("í", "i").replace("ï", "i")
          .replace("ú", "u").replace("ç", "c").replace("ñ", "n"))
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


# ---------- PDF acquisition ----------

def discover_pdf_url() -> str | None:
    req = urllib.request.Request(DOC_URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 — network failure is non-fatal; caller falls back
        log(f"  could not load documentation page: {exc}")
        return None
    m = PDF_LINK_RE.search(html)
    return m.group(1) if m else None


def download_pdf(url: str, dest: Path) -> Path | None:
    log(f"  downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.write_bytes(resp.read())
    except Exception as exc:  # noqa: BLE001 — network failure is non-fatal; caller reports + exits
        log(f"  download failed: {exc}")
        return None
    log(f"  saved {dest} ({dest.stat().st_size / 1024 / 1024:.1f} MiB)")
    return dest


def list_stand(source: str) -> str | None:
    m = STAND_RE.search(source)
    return m.group(1) if m else None


# ---------- PDF parsing ----------

def classify(row: dict) -> str:
    blob = " ".join((row.get(c) or "") for c in COLS)
    if "Stolperschwelle" in blob:
        return "stolperschwelle"
    if "Kopfstein" in blob:
        return "kopfstein"
    return "stolperstein"


def parse_pdf(path: Path) -> list[dict]:
    """Return one dict per table row, keyed by COLS, with a ``marker_type``."""
    rows: list[dict] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables():
                for raw in tbl:
                    if not raw or not (raw[0] or "").strip():
                        continue
                    if (raw[0] or "").strip().startswith("Name, Vorname"):
                        continue  # repeated header
                    cells = [(c or "").replace("\n", " ").strip() for c in raw]
                    row = {COLS[i]: cells[i] for i in range(min(len(COLS), len(cells)))}
                    if not row.get("address"):
                        continue  # section dividers ('Stolperschwellen und Kopfsteine:') carry no address
                    row["marker_type"] = classify(row)
                    rows.append(row)
    return rows


# ---------- Field parsing ----------

def parse_de_date(raw: str) -> str | None:
    """German date → ISO. Full date when known, else year, else None."""
    s = (raw or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.search(r"(\d{4})", s)
    return m.group(1) if m else None


# Non-date markers that appear in the Todesdatum column instead of a date.
_GROUP_MARKERS = ("T4", "§175", "175", "Widerstand", "asozial", "BV")


def parse_death(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s or any(mk.lower() in s.lower() for mk in _GROUP_MARKERS):
        return None
    return parse_de_date(s)


def victim_group(death_cell: str, fate: str) -> str:
    blob = f"{death_cell} {fate}".lower()
    if "sinti" in blob or "roma" in blob:
        return "Sinti/Roma"
    if "t4" in (death_cell or "").lower() or "euthanas" in blob:
        return "T4 (Krankenmorde)"
    if "§175" in blob or "homosex" in blob:
        return "§175 (homosexuell verfolgt)"
    if "widerstand" in blob or "politisch" in blob:
        return "politisch verfolgt"
    if "asozial" in blob or re.search(r"\bbv\b", blob):
        return "als 'asozial'/'BV' verfolgt"
    return "jüdisch verfolgt"


def display_name(name_cell: str) -> str:
    """'Lastname, Given Names' → 'Given Names Lastname'. Keeps titles."""
    s = (name_cell or "").strip()
    if "," not in s:
        return s
    last, given = s.split(",", 1)
    given = re.sub(r"\s+", " ", given.replace(",", " ")).strip()
    last = last.strip()
    return f"{given} {last}".strip()


def lastname_tokens(name_cell: str) -> set[str]:
    last = (name_cell or "").split(",", 1)[0]
    return {t for t in slugify(last).split("-") if t}


def given_tokens(name_cell: str) -> list[str]:
    s = (name_cell or "")
    given = s.split(",", 1)[1] if "," in s else ""
    return [t for t in slugify(given).split("-") if t and t not in TITLE_TOKENS]


def name_key(name: str, is_cell: bool) -> set[str]:
    if is_cell:
        toks = list(lastname_tokens(name)) + given_tokens(name)
    else:
        toks = slugify(name).split("-")
    return {t for t in toks if t and t not in TITLE_TOKENS}


def parse_address(addr_cell: str) -> dict:
    s = re.sub(r"\s*\([^)]*\)", "", addr_cell or "").strip()  # drop parentheticals
    m = re.match(r"^(.*?)\s+(\d+\s*\w?(?:\s*[-–/]\s*\d+\s*\w?)?)$", s)
    if m:
        street, house = m.group(1).strip(), re.sub(r"\s+", "", m.group(2))
    else:
        street, house = s, ""
    return {
        "street": street,
        "house_number": house,
        "postcode": None,
        "district": None,
        "formatted": " ".join(x for x in (street, house) if x),
    }


def addr_slug(address: dict) -> str:
    return "-".join(p for p in (slugify(address["street"]), slugify(address["house_number"])) if p)


def street_core(street: str) -> str:
    """Collapse street-name spelling variants ('Berger Straße' vs 'Bergerstraße',
    'Bolongarostr.' vs 'Bolongarostraße') to a stable core for address matching."""
    core = slugify(street).replace("-", "")
    return re.sub(r"(strasse|str)$", "", core)


def addr_key(address: dict) -> str:
    """Normalized address key for matching/coords (tolerates street-spelling drift)."""
    return "-".join(p for p in (street_core(address["street"]), slugify(address["house_number"])) if p)


# ---------- Existing-record index ----------

def load_existing(city_dir: Path) -> dict:
    """Index existing records for matching.

    Returns a dict of indices (entry dicts are shared, so the ``claimed`` flag is
    visible across every index that references the same record):
      by_address: addr_key (street_core + house) → [entry]
      by_street:  street_core → [entry]
      by_birth:   full ISO birth date (YYYY-MM-DD) → [entry]
      by_marker:  "addr_key|marker_type" → [entry]
      coords:     addr_key → [lat, lng]
      paths:      record id → Path
    """
    idx = {"by_address": {}, "by_street": {}, "by_birth": {}, "by_marker": {}, "coords": {}, "paths": {}}
    if not city_dir.exists():
        return idx
    for path in sorted(city_dir.glob("*.json")):
        try:
            rec = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        idx["paths"][rec.get("id", path.stem)] = path
        a = rec.get("address") or {}
        akey = addr_key({"street": a.get("street") or "", "house_number": a.get("house_number") or ""})
        if not akey:
            continue
        entry = {"record": rec, "path": path, "claimed": False}
        idx["by_address"].setdefault(akey, []).append(entry)
        idx["by_street"].setdefault(street_core(a.get("street") or ""), []).append(entry)
        birth = (rec.get("person") or {}).get("birth_date") or ""
        if len(birth) == 10:
            idx["by_birth"].setdefault(birth, []).append(entry)
        if rec.get("marker_type"):
            idx["by_marker"].setdefault(f"{akey}|{rec['marker_type']}", []).append(entry)
        if rec.get("coords") and akey not in idx["coords"]:
            idx["coords"][akey] = rec["coords"]
    return idx


def seed_coords_from_cache(coord_by_addr: dict) -> int:
    if not COORD_CACHE_PATH.exists():
        return 0
    try:
        cache = json.loads(COORD_CACHE_PATH.read_text())
    except json.JSONDecodeError:
        return 0
    added = 0
    for addr, coords in cache.items():
        akey = addr_key(parse_address(addr))
        if akey and akey not in coord_by_addr and coords:
            coord_by_addr[akey] = [round(float(coords[0]), 7), round(float(coords[1]), 7)]
            added += 1
    return added


# ---------- Matching + record assembly ----------

def _years_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a[:4] == b[:4]


def _cand_name_key(cand: dict) -> set[str]:
    return name_key(cand["record"]["person"]["name"], is_cell=False)


def find_match(idx: dict, row: dict) -> dict | None:
    """Resolve the existing record for a victim row, tolerant of source conflicts.

    Tier 1 — same address: strict surname + first-given match (best key overlap);
    else a single remaining candidate sharing the first given name (absorbs
    surname-spelling drift like Eiseman/Eisemann while keeping distinct relatives,
    e.g. Anneliese vs Melanie Vollmer, apart).
    Tier 2 — same street, any house number: house numbers disagree between OSM and
    the Initiative (e.g. Alt-Heddernheim 31 vs 33), so fall back to a unique
    surname + first-given match on the street, disambiguated by birth year.
    Tier 3 — city-wide by exact birth date: addresses sometimes diverge entirely
    between sources (Berger Spielhaus 7 vs Alt-Bergen 6), so a unique record with
    the identical full birth date AND matching surname + first given name is
    accepted. Surname+given+exact-DD.MM.YYYY is a person identity — surname alone
    is not (two unrelated Baers can share a birth date), so all three are required.
    """
    address = parse_address(row["address"])
    last = lastname_tokens(row["name"])
    given = given_tokens(row["name"])
    first = given[0] if given else None
    want = name_key(row["name"], is_cell=True)
    birth = parse_de_date(row["birth_date"])

    def named(pool):
        return [c for c in pool if not c["claimed"] and (c["record"].get("person") or {}).get("name")]

    # Tier 1 — exact address.
    addr_named = named(idx["by_address"].get(addr_key(address), []))
    best, best_score = None, 0
    for cand in addr_named:
        ckey = _cand_name_key(cand)
        if not (last & ckey) or (first and first not in ckey):
            continue
        score = len(want & ckey) + (2 if want == ckey else 0)
        if score > best_score:
            best, best_score = cand, score
    if best is not None:
        return best
    loose = [c for c in addr_named if first and first in _cand_name_key(c)]
    if len(loose) == 1:
        return loose[0]

    # Tier 2 — same street.
    street_named = [c for c in named(idx["by_street"].get(street_core(address["street"]), []))
                    if (last & _cand_name_key(c)) and (not first or first in _cand_name_key(c))]
    if len(street_named) == 1:
        return street_named[0]
    if len(street_named) > 1 and birth:
        by_year = [c for c in street_named if _years_match(birth, (c["record"].get("person") or {}).get("birth_date"))]
        if len(by_year) == 1:
            return by_year[0]

    # Tier 3 — city-wide, exact birth date + full name agreement.
    if birth and len(birth) == 10:
        bp = [c for c in named(idx["by_birth"].get(birth, []))
              if (last & _cand_name_key(c)) and (first and first in _cand_name_key(c))]
        if len(bp) == 1:
            return bp[0]
    return None


def find_marker_match(idx: dict, row: dict) -> dict | None:
    """Match an existing marker record (Stolperschwelle/Kopfstein) by address + type."""
    akey = addr_key(parse_address(row["address"]))
    for cand in idx["by_marker"].get(f"{akey}|{row['marker_type']}", []):
        if not cand["claimed"]:
            return cand
    return None


def enrich_record(rec: dict, row: dict, stand: str | None) -> list[str]:
    """Fill empty fields from the Initiative row. Returns the list of filled keys."""
    filled: list[str] = []
    person = rec.setdefault("person", {})
    is_person = not rec.get("marker_type")

    def fill(obj: dict, key: str, value):
        if value and not obj.get(key):
            obj[key] = value
            filled.append(key)

    if is_person:
        fill(person, "birth_date", parse_de_date(row["birth_date"]))
        fill(person, "death_date", parse_death(row["death_date"]))
        fill(person, "birth_name", row.get("birth_name") or None)
        fill(person, "victim_group", victim_group(row.get("death_date", ""), row.get("fate", "")))
    fill(person, "fate", row.get("fate") or None)
    fill(rec.setdefault("address", {}), "district", row.get("district") or None)
    fill(rec, "laying_date", parse_de_date(row["laying_date"]))

    rec.setdefault("enrichers", {})[SOURCE_KEY] = {
        "fetched_at": now_iso(),
        "list_stand": stand,
        "found": True,
    }
    return filled


def build_record(row: dict, coords: list | None, slug: str) -> dict:
    address = parse_address(row["address"])
    address["district"] = row.get("district") or None
    marker = row["marker_type"]
    is_person = marker == "stolperstein"

    person = {
        "name": display_name(row["name"]) if is_person else (row["name"] or None),
        "birth_date": parse_de_date(row["birth_date"]) if is_person else None,
        "death_date": parse_death(row["death_date"]) if is_person else None,
        "birth_place": None,
        "death_place": None,
        "birth_name": (row.get("birth_name") or None) if is_person else None,
        "fate": row.get("fate") or None,
        "victim_group": victim_group(row.get("death_date", ""), row.get("fate", "")) if is_person else None,
    }

    return {
        "id": f"{CITY_SLUG}/{slug}",
        "city": CITY_SLUG,
        "city_name": CITY_NAME,
        "country": None,
        "coords": coords,
        "coords_source": "address-match" if coords else "none",
        "person": person,
        "address": address,
        "marker_type": None if is_person else marker,
        "inscription": None,
        "laying_date": parse_de_date(row["laying_date"]),
        "artist": None,
        "material": None,
        "refs": {
            "osm_id": None, "osm_version": None, "wikidata": None, "wikipedia": None,
            "wikimedia_commons": None, "image": None,
            "website": "https://www.stolpersteine-frankfurt.de/de/dokumentation",
            "network": None,
        },
        "biographies": [],
        "images": [],
        "enrichers": {SOURCE_KEY: {"fetched_at": now_iso(), "list_stand": list_stand_global, "found": True}},
    }


def new_slug(row: dict, address: dict, taken: set[str]) -> str:
    base = addr_slug(address)
    if row["marker_type"] == "stolperstein":
        suffix = slugify(display_name(row["name"]))
    else:
        suffix = slugify(f"{row['marker_type']}-{row['name']}")
    slug = "-".join(p for p in (base, suffix) if p) or slugify(row["name"]) or "unbekannt"
    slug = slug[:120].rstrip("-")
    candidate, n = slug, 2
    while candidate in taken:
        candidate = f"{slug}-{n}"
        n += 1
    taken.add(candidate)
    return candidate


list_stand_global: str | None = None


# ---------- Main ----------

def main() -> int:
    global list_stand_global
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", type=Path, default=None, help="Parse a local Gesamtliste PDF instead of downloading.")
    ap.add_argument("--url", default=None, help="Override the PDF URL (default: discover from documentation page).")
    ap.add_argument("--dry-run", action="store_true", help="Parse + match but write no files.")
    ap.add_argument("--limit", type=int, default=None, help="Process only the first N rows (debugging).")
    args = ap.parse_args()

    # 1. Acquire the PDF.
    if args.pdf:
        pdf_path = args.pdf
        list_stand_global = list_stand(pdf_path.name)
        log(f"Parsing local PDF {pdf_path}")
    else:
        url = args.url or discover_pdf_url()
        if not url:
            log("FATAL: could not discover the Gesamtliste PDF URL; pass --pdf or --url.")
            return 1
        list_stand_global = list_stand(url)
        pdf_path = download_pdf(url, DATA_DIR / "stolpersteine-frankfurt-gesamtliste.pdf")
        if pdf_path is None:
            log("FATAL: could not download the Gesamtliste PDF; retry later or pass --pdf.")
            return 1
    log(f"  list stand: {list_stand_global or 'unknown'}")

    # 2. Parse rows.
    rows = parse_pdf(pdf_path)
    if args.limit:
        rows = rows[: args.limit]
    persons = [r for r in rows if r["marker_type"] == "stolperstein"]
    markers = [r for r in rows if r["marker_type"] != "stolperstein"]
    log(f"Parsed {len(rows)} rows: {len(persons)} victims, {len(markers)} Stolperschwellen/Kopfsteine")

    # 3. Index existing records.
    city_dir = RECORDS_DIR / CITY_SLUG
    idx = load_existing(city_dir)
    seeded = seed_coords_from_cache(idx["coords"])
    log(f"Indexed {sum(len(v) for v in idx['by_address'].values())} existing records across "
        f"{len(idx['by_address'])} addresses; {len(idx['coords'])} known coords (+{seeded} from cache)")

    taken_slugs = {p.stem for p in city_dir.glob("*.json")} if city_dir.exists() else set()

    stats = {"enriched": 0, "enriched_fields": 0, "created_person": 0, "created_marker": 0,
             "new_with_coords": 0, "new_without_coords": 0, "unchanged_match": 0}
    to_write: list[tuple[Path, dict]] = []

    for row in rows:
        match = find_match(idx, row) if row["marker_type"] == "stolperstein" else find_marker_match(idx, row)

        if match is not None:
            match["claimed"] = True
            filled = enrich_record(match["record"], row, list_stand_global)
            stats["enriched_fields"] += len(filled)
            if filled:
                stats["enriched"] += 1
            else:
                stats["unchanged_match"] += 1
            to_write.append((match["path"], match["record"]))
            continue

        # No match → new record.
        address = parse_address(row["address"])
        address["district"] = row.get("district") or None
        akey = addr_key(address)
        birth = parse_de_date(row["birth_date"])
        coords = idx["coords"].get(akey)
        slug = new_slug(row, address, taken_slugs)
        rec = build_record(row, coords, slug)
        path = city_dir / f"{slug}.json"
        to_write.append((path, rec))
        if row["marker_type"] == "stolperstein":
            stats["created_person"] += 1
        else:
            stats["created_marker"] += 1
        stats["new_with_coords" if coords else "new_without_coords"] += 1
        # Make the freshly-created record matchable for siblings in this same run.
        entry = {"record": rec, "path": path, "claimed": True}
        idx["by_address"].setdefault(akey, []).append(entry)
        idx["by_street"].setdefault(street_core(address["street"]), []).append(entry)
        if birth and len(birth) == 10:
            idx["by_birth"].setdefault(birth, []).append(entry)
        if rec.get("marker_type"):
            idx["by_marker"].setdefault(f"{akey}|{rec['marker_type']}", []).append(entry)

    # 4. Report.
    log("Summary:")
    log(f"  enriched existing records : {stats['enriched']} ({stats['enriched_fields']} fields filled)")
    log(f"  matched, already complete : {stats['unchanged_match']}")
    log(f"  new victim records        : {stats['created_person']}")
    log(f"  new marker records        : {stats['created_marker']}")
    log(f"    with coords (addr-match): {stats['new_with_coords']}")
    log(f"    without coords          : {stats['new_without_coords']}")

    if args.dry_run:
        log("Dry run — no files written.")
        return 0

    city_dir.mkdir(parents=True, exist_ok=True)
    for path, rec in to_write:
        path.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    log(f"Wrote {len(to_write)} record files → {city_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
