#!/usr/bin/env python3
"""Report consistency problems in data/stolpersteine-records/.

Read-only. Never modifies records. Exits 1 when problems are found so it can
serve as a CI gate later.

Usage:
    uv run scripts/check_records.py [--city CITY] [--json]
"""

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _slug import slugify  # noqa: E402  (needs the sys.path line above)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECORDS_DIR = DATA_DIR / "stolpersteine-records"


def load_records(city: str | None) -> tuple[list[tuple[Path, dict]], int]:
    """Return (records, corrupt_count). Diagnostics go to stderr, never stdout,
    so --json output stays machine-parseable."""
    pattern = f"{city}/*.json" if city else "*/*.json"
    out: list[tuple[Path, dict]] = []
    corrupt = 0
    for path in sorted(RECORDS_DIR.glob(pattern)):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  CORRUPT {path}: {exc}", file=sys.stderr)
            corrupt += 1
            continue
        if not isinstance(payload, dict):
            print(f"  CORRUPT {path}: expected a JSON object", file=sys.stderr)
            corrupt += 1
            continue
        out.append((path, payload))
    return out, corrupt


def addr_key(record: dict) -> tuple[str, str]:
    address = record.get("address") or {}
    return (slugify(address.get("street")), slugify(address.get("house_number")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", help="restrict to one city slug")
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args()

    if not RECORDS_DIR.is_dir():
        print(f"ERROR: {RECORDS_DIR} does not exist", file=sys.stderr)
        return 1

    records, corrupt = load_records(args.city)
    if not records:
        print("ERROR: no records found — wrong path, or the archive is missing", file=sys.stderr)
        return 1
    by_address: dict[tuple[str, str], list[tuple[Path, dict]]] = collections.defaultdict(list)
    for path, record in records:
        by_address[addr_key(record)].append((path, record))

    anonymous = [(p, r) for p, r in records if not (r.get("person") or {}).get("name")]
    orphan_bios = [(p, r) for p, r in anonymous if r.get("biographies")]
    no_coords = [(p, r) for p, r in records if not r.get("coords")]

    split_locations = []
    for key, group in sorted(by_address.items()):
        if key == ("", ""):
            continue
        named = [(p, r) for p, r in group if (r.get("person") or {}).get("name")]
        anon = [(p, r) for p, r in group if not (r.get("person") or {}).get("name")]
        if named and anon:
            split_locations.append((key, [p.name for p, _ in anon], [p.name for p, _ in named]))

    report = {
        "records": len(records),
        "corrupt_files": corrupt,
        "anonymous_records": len(anonymous),
        "biographies_on_anonymous_records": sum(
            len(r.get("biographies") or []) for _, r in orphan_bios
        ),
        "records_without_coords": len(no_coords),
        "split_locations": len(split_locations),
    }

    if args.json:
        print(json.dumps({**report, "details": split_locations}, ensure_ascii=False, indent=2))
    else:
        print(f"records:                            {report['records']}")
        print(f"corrupt files (skipped):            {report['corrupt_files']}")
        print(f"anonymous (person.name is null):    {report['anonymous_records']}")
        print(f"biographies stranded on anonymous:  {report['biographies_on_anonymous_records']}")
        print(f"records without coordinates:        {report['records_without_coords']}")
        print(f"addresses split anon+named:         {report['split_locations']}")
        for key, anon, named in split_locations[:20]:
            print(f"  {key[0]} {key[1]}\n     anon:  {anon}\n     named: {named}")
        if len(split_locations) > 20:
            print(f"  ... and {len(split_locations) - 20} more")

    return 1 if (split_locations or corrupt) else 0


if __name__ == "__main__":
    raise SystemExit(main())
