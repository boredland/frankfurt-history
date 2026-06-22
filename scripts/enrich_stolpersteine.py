#!/usr/bin/env python3
"""Enrich Stolpersteine records with initiative-scraped biographies.

Walks ``data/stolpersteine-records/<city>/*.json``, dispatches each record
to whichever initiative scraper claims its ``refs.website`` host, and
merges the returned enrichment blob back into the record.

Usage:
    uv run scripts/enrich_stolpersteine.py                          # all cities, all scrapers
    uv run scripts/enrich_stolpersteine.py --city berlin            # one city
    uv run scripts/enrich_stolpersteine.py --city berlin --limit 5  # smoke test
    uv run scripts/enrich_stolpersteine.py --refetch                # re-run even if already enriched
"""

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECORDS_DIR = DATA_DIR / "stolpersteine-records"

# Import the initiatives package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import initiatives  # noqa: E402

_start = time.monotonic()


def log(msg: str) -> None:
    m, s = divmod(int(time.monotonic() - _start), 60)
    print(f"[{m:02d}:{s:02d}] {msg}", flush=True)


def discover_scrapers() -> list:
    """Import every module in the initiatives package and instantiate its Scraper."""
    scrapers = []
    pkg_path = Path(initiatives.__file__).resolve().parent
    for info in pkgutil.iter_modules([str(pkg_path)]):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"initiatives.{info.name}")
        cls = getattr(mod, "Scraper", None)
        if cls is not None:
            scrapers.append(cls())
    return scrapers


def pick_scraper(scrapers, url: str):
    for s in scrapers:
        if s.can_handle(url):
            return s
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- Merging ----------

def merge_enrichment(record: dict, enr: dict, source_key: str, source_host: str) -> dict:
    """Apply an EnrichmentResult to a record, replacing prior contributions from the same source."""
    # Biographies: drop anything previously contributed by this source, then append new ones.
    # Bios from other sources are preserved.
    kept_bios = [b for b in (record.get("biographies") or []) if b.get("source") != source_host]
    new_bios = enr.get("biographies") or []
    # De-dup the combined set by source_url to defend against double-runs in the same batch.
    seen_urls: set[str] = set()
    merged_bios: list[dict] = []
    for b in kept_bios + new_bios:
        key = b.get("source_url") or id(b)
        if key in seen_urls:
            continue
        seen_urls.add(key)
        merged_bios.append(b)
    record["biographies"] = merged_bios

    kept_imgs = [im for im in (record.get("images") or []) if im.get("source") != source_host]
    new_imgs = enr.get("images") or []
    seen_img_urls: set[str] = set()
    merged_imgs: list[dict] = []
    for im in kept_imgs + new_imgs:
        u = im.get("url")
        if not u or u in seen_img_urls:
            continue
        seen_img_urls.add(u)
        merged_imgs.append(im)
    record["images"] = merged_imgs

    # Person updates: only fill in null/missing fields (don't overwrite OSM values).
    person = record.setdefault("person", {})
    for k, v in (enr.get("person_updates") or {}).items():
        if v in (None, "", [], {}):
            continue
        if person.get(k) in (None, "", [], {}):
            person[k] = v

    # Address updates: same fill-don't-overwrite rule.
    address = record.setdefault("address", {})
    for k, v in (enr.get("address_updates") or {}).items():
        if v in (None, "", [], {}):
            continue
        if address.get(k) in (None, "", [], {}):
            address[k] = v

    # Laying date: only if currently null.
    laying = (enr.get("extras") or {}).get("laying_date_iso")
    if laying and not record.get("laying_date"):
        record["laying_date"] = laying

    # Enricher provenance.
    enrichers = record.setdefault("enrichers", {})
    enrichers[source_key] = {
        "fetched_at": now_iso(),
        "found": bool(new_bios) or bool(new_imgs),
        "bios": len(new_bios),
        "images": len(new_imgs),
    }
    return record


# ---------- Worker ----------

def process_record(path: Path, scrapers, refetch: bool) -> tuple[str, str]:
    """Returns (status, detail) for logging."""
    try:
        record = json.loads(path.read_text())
    except json.JSONDecodeError:
        return "error", "invalid json"

    url = (record.get("refs") or {}).get("website") or ""
    scraper = pick_scraper(scrapers, url)
    if not scraper:
        return "skip", "no scraper"

    if not refetch and scraper.source_key in (record.get("enrichers") or {}):
        prior = record["enrichers"][scraper.source_key]
        if prior.get("found"):
            return "cached", scraper.source_key

    try:
        enr = scraper.fetch(record)
    except Exception as e:
        return "error", f"{scraper.source_key}: {e!r}"

    if not enr:
        # Mark as attempted-but-empty to avoid re-fetching dead URLs on every run.
        record.setdefault("enrichers", {})[scraper.source_key] = {
            "fetched_at": now_iso(), "found": False, "bios": 0, "images": 0,
        }
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        return "miss", scraper.source_key

    record = merge_enrichment(record, enr, scraper.source_key, scraper.host)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    return "ok", f"{scraper.source_key}: {len(enr.get('biographies') or [])} bios, {len(enr.get('images') or [])} imgs"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", help="Only process records for this city slug (e.g. berlin)")
    ap.add_argument("--limit", type=int, default=None, help="Stop after this many records")
    ap.add_argument("--workers", type=int, default=4, help="Parallel HTTP workers (be polite)")
    ap.add_argument("--refetch", action="store_true", help="Re-scrape even when already enriched successfully")
    args = ap.parse_args()

    scrapers = discover_scrapers()
    log(f"Loaded {len(scrapers)} initiative scrapers: {[s.host for s in scrapers]}")

    if args.city:
        cities = [RECORDS_DIR / args.city]
    else:
        cities = [p for p in RECORDS_DIR.iterdir() if p.is_dir()]

    paths: list[Path] = []
    for c in cities:
        if not c.exists():
            log(f"  WARN: {c} doesn't exist, skipping")
            continue
        paths.extend(sorted(c.glob("*.json")))
    if args.limit:
        paths = paths[: args.limit]
    log(f"Processing {len(paths)} records across {len(cities)} cities")

    counts = {"ok": 0, "miss": 0, "skip": 0, "cached": 0, "error": 0}
    processed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_record, p, scrapers, args.refetch): p for p in paths}
        for fut in as_completed(futures):
            path = futures[fut]
            status, detail = fut.result()
            counts[status] = counts.get(status, 0) + 1
            processed += 1
            if status in {"ok", "miss", "error"}:
                log(f"  {status.upper()} {path.parent.name}/{path.stem} — {detail}")
            if processed % 50 == 0:
                log(f"  Progress: {processed}/{len(paths)} — {counts}")

    log(f"Done. {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
