# Plan 004: Audit and report Stolpersteine record fragmentation (investigate, do not migrate)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat a44900bf..HEAD -- scripts/ data/stolpersteine-records/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW (this plan writes a report and a checker; it does not rewrite records)
- **Depends on**: plans/001-verification-baseline.md (needs pytest configured)
- **Category**: bug
- **Planned at**: commit `a44900bf`, 2026-08-16

## Why this matters

`data/stolpersteine-records/` holds 2,868 JSON records about Holocaust victims,
built by five scripts that each construct filenames with their **own** copy of
`slugify()`. Those copies disagree, and nothing detects a filename collision
before writing. Three defects were confirmed against the live data:

1. **Slug divergence splits one stone into two records.** `Linnéstraße` becomes
   `linnestrasse` in `fetch_osm_stolpersteine.py` but `linn-strasse` in
   `migrate_ffm_to_records.py`. Real consequence:
   `linn-strasse-27.json` carries 1 biography and 3 images with
   `person.name: null`, while `linnestrasse-27-wilhelm-adam-hugo.json` carries
   the victim's name and zero biographies. Same physical stone, same address,
   two records, neither complete.
2. **Silent overwrite on collision.** `migrate_ffm_to_records.py` pass 2 writes
   `(RECORDS_DIR / f"{slug}.json").write_text(...)` with no existence check. Two
   of 793 WFS entries collide (`bornheimer-landwehr-85`,
   `schwanheimer-strasse-65`); the second write destroys the first.
3. **Systemic fragmentation.** 463 addresses hold both an anonymous
   location-level record (`person.name: null`) and named stone records. 521 of
   1,201 biographies sit on those anonymous records, which
   `fetch_initiative_stolpersteine.py:344` explicitly filters out of matching —
   so those biographies can never be attached to the person they describe.

For a memorial archive, a biography detached from its victim's name is the
defect that matters most. **This plan does not fix it.** A repair that rewrites
2,868 committed records is not something to attempt without first knowing the
exact blast radius. This plan produces that: a permanent consistency checker, a
written report of every affected record, and a unified `slugify` that stops the
divergence getting worse. The actual record merge is a follow-up, scoped by this
plan's output.

## Current state

**The five divergent `slugify` implementations**, verbatim:

`archive.py:152-161` — keeps non-ASCII via `\w`, truncates at 80:

```python
def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[äÄ]", "ae", text)
    text = re.sub(r"[öÖ]", "oe", text)
    text = re.sub(r"[üÜ]", "ue", text)
    text = re.sub(r"[ß]", "ss", text)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80].strip("-")
```

`scripts/build_stolpersteine.py:55-59` and
`scripts/migrate_ffm_to_records.py:43-47` — identical to each other; umlauts
only, **no** accented-Latin folding, no truncation:

```python
def slugify(text: str) -> str:
    s = text.lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
```

`scripts/fetch_osm_stolpersteine.py:129-139` — adds accented-Latin folding:

```python
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
```

`scripts/fetch_initiative_stolpersteine.py:72-82` — same as the OSM one **plus**
`(text or "")`, so it is the only one that survives `None`.

Because `migrate_ffm_to_records.py` lacks the accent folding, `Linnéstraße`
→ `linn-strasse` there but `linnestrasse` in the OSM script. That single
difference produces defect 1.

**The unguarded write.** `scripts/migrate_ffm_to_records.py:268-270`:

```python
        (RECORDS_DIR / f"{slug}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n"
        )
```

Compare `scripts/fetch_initiative_stolpersteine.py:461-474`, which **does**
handle collisions and is the pattern to follow:

```python
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
```

**The matching filter that strands anonymous records.**
`scripts/fetch_initiative_stolpersteine.py:343-344`:

```python
    def named(pool):
        return [c for c in pool if not c["claimed"] and (c["record"].get("person") or {}).get("name")]
```

**Record schema** (top-level keys, confirmed across all 2,868 files): `id`,
`city`, `city_name`, `country`, `coords`, `coords_source`, `person`, `address`,
`marker_type` (1,614 records), `inscription`, `laying_date`, `artist`,
`material`, `refs`, `biographies`, `images`, `enrichers`, `commemorates` (527).
`coords_source` values: `address-match` 1254, `osm` 727, `wfs` 527, `none` 360.

**Repo conventions you must match:**

- Python 3.12+, 4-space indent, type hints, `pathlib.Path`, f-strings,
  `SCREAMING_CASE` module constants. Package manager is `uv`.
- Scripts are standalone with a `main()` and `if __name__ == "__main__":`.
  Argument parsing uses `argparse` — see
  `scripts/enrich_stolpersteine.py:168-173` for the house style.
- Logging is a module-level `log()` writing an elapsed `[mm:ss]` prefix — see
  `scripts/fetch_osm_stolpersteine.py:88-91`.
- Commit style: Conventional Commits, e.g.
  `feat: add stolpersteine record consistency checker`.
- **Never modify anything under `data/`** in this plan.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run tests | `uv run pytest -q` | exit 0 |
| Run the new checker | `uv run scripts/check_records.py` | exits 0 or 1, prints a summary |
| Count records | `ls data/stolpersteine-records/frankfurt-am-main/*.json \| wc -l` | `2868` |

## Scope

**In scope**:

- `scripts/_slug.py` (create — the single shared slug implementation)
- `scripts/check_records.py` (create — the consistency checker)
- `tests/test_slug.py` (create)
- `tests/test_check_records.py` (create)
- `scripts/migrate_ffm_to_records.py` (modify — **only** the two changes in
  steps 3 and 4: import the shared slugify, and refuse to overwrite)
- `plans/004-findings.md` (create — the report this plan produces)

**Out of scope** (do NOT touch, even though they look related):

- **Any file under `data/`.** This plan does not repair a single record. It
  measures. Rewriting 2,868 committed memorial records is a follow-up that this
  plan's report will scope.
- `archive.py`'s `slugify` — it names *theme article* files under
  `data/de/**`, a different namespace with 3,637 committed filenames. Changing
  it would rename committed content. Leave it.
- `scripts/build_stolpersteine.py`, `scripts/fetch_osm_stolpersteine.py`,
  `scripts/fetch_initiative_stolpersteine.py` — do NOT switch these to the
  shared slugify in this plan. `fetch_osm_stolpersteine.py`'s slug already
  matches 727 committed filenames; changing it would orphan them. Only
  `migrate_ffm_to_records.py` changes here, because it is the one that is
  *wrong* relative to the others.
- `.github/workflows/archive.yml` — do not wire the checker into the cron yet.
  Let it run manually first.

## Git workflow

- Branch: `advisor/004-record-identity-audit`
- Commit per step; Conventional Commits, e.g.
  `feat: add shared slugify and record consistency checker`,
  `fix: prevent silent record overwrite in ffm migration`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Create the shared slug module

Create `scripts/_slug.py`. Its behaviour must match
`scripts/fetch_osm_stolpersteine.py`'s implementation exactly — that one already
names 727 committed files, so it is the de-facto standard — plus the `None`
guard from `fetch_initiative_stolpersteine.py`:

```python
"""Single source of truth for record slug construction.

Historically each pipeline script carried its own copy of ``slugify``. They
disagreed on accented-Latin folding, which split one physical stone across two
record files (e.g. Linnéstraße -> ``linnestrasse`` vs ``linn-strasse``).

This implementation matches scripts/fetch_osm_stolpersteine.py, which already
names the majority of committed records. Changing it renames files on disk —
do not "improve" it without a migration.
"""

import re

_FOLD = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "á": "a", "à": "a", "â": "a",
    "é": "e", "è": "e", "ê": "e",
    "ó": "o", "ô": "o",
    "í": "i", "ï": "i",
    "ú": "u", "ç": "c", "ñ": "n",
}


def slugify(text: str | None) -> str:
    """ASCII kebab-case slug. Folds German umlauts and accented Latin letters."""
    s = (text or "").lower()
    for src, dst in _FOLD.items():
        s = s.replace(src, dst)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
```

**Verify**: `uv run python3 -c "import sys; sys.path.insert(0,'scripts'); from _slug import slugify; print(slugify('Linnéstraße'), slugify(None), slugify('Bornheimer Landwehr'))"`
→ prints `linnestrasse  bornheimer-landwehr` (note the empty middle value).

### Step 2: Write tests for the shared slug

Create `tests/test_slug.py`, using the `load_script` helper from
`tests/conftest.py` created in plan 001:

```python
"""Tests for the shared slug implementation."""

import pytest

from tests.conftest import load_script

slug_mod = load_script("slug_mod", "scripts/_slug.py")
slugify = slug_mod.slugify


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Linnéstraße", "linnestrasse"),
        ("Bornheimer Landwehr", "bornheimer-landwehr"),
        ("Schwanheimer Straße", "schwanheimer-strasse"),
        ("René Bienes", "rene-bienes"),
        ("Müller", "mueller"),
        ("Öderweg", "oederweg"),
        ("", ""),
        (None, ""),
        ("   ", ""),
        ("---", ""),
        ("../etc/passwd", "etc-passwd"),
        ("a/b\\c", "a-b-c"),
    ],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected


def test_slugify_never_emits_path_separators_or_dots():
    for raw in ["../..", "./x", "a/../b", "..", "."]:
        out = slugify(raw)
        assert "/" not in out
        assert "\\" not in out
        assert out not in {".", ".."}


def test_slugify_matches_osm_script_for_committed_names():
    """The shared implementation must reproduce the OSM script's slugs."""
    osm = load_script("osm_mod_slugcheck", "scripts/fetch_osm_stolpersteine.py")
    for raw in ["Linnéstraße", "Müller", "René Bienes", "Bornheimer Landwehr"]:
        assert slugify(raw) == osm.slugify(raw)
```

**Verify**: `uv run pytest tests/test_slug.py -q` → exit 0, all pass.

If `test_slugify_matches_osm_script_for_committed_names` fails, the shared
implementation diverges from the one that named the committed files. Fix
`scripts/_slug.py` to match the OSM script, not the other way round.

### Step 3: Point `migrate_ffm_to_records.py` at the shared slug

In `scripts/migrate_ffm_to_records.py`, **delete** the local `slugify`
definition at lines 43-47 and import the shared one instead. Add near the other
imports, following the `sys.path` pattern already used by
`scripts/enrich_stolpersteine.py:31`:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _slug import slugify
```

(Add `import sys` if it is not already imported.)

Do not change `addr_slug` or any other function — only the `slugify` it calls.

**Verify**:
- `grep -n "^def slugify" scripts/migrate_ffm_to_records.py` → no matches.
- `uv run python3 -c "import importlib.util,sys; sys.path.insert(0,'scripts'); spec=importlib.util.spec_from_file_location('m','scripts/migrate_ffm_to_records.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(m.addr_slug('Linnéstraße','27'))"`
  → prints `linnestrasse-27` (previously `linn-strasse-27`).

**This changes future filenames but does not rename existing files.** That is
expected and is precisely what the step-5 report must quantify.

### Step 4: Make the unguarded write refuse to destroy a record

In `scripts/migrate_ffm_to_records.py`, replace the pass-2 write at lines
268-270:

```python
        (RECORDS_DIR / f"{slug}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n"
        )
```

with a collision-aware write that follows the `new_slug` pattern already used in
`scripts/fetch_initiative_stolpersteine.py:461-474`:

```python
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
```

A loud log line plus a distinct filename is the goal: never silently lose a
victim record.

**Verify**: `grep -n "COLLISION" scripts/migrate_ffm_to_records.py` → one match.

**Also verify idempotence.** This script runs on every weekly cron
(`.github/workflows/archive.yml:52`) against the committed records, so a
collision handler that allocates a *new* suffix on each run would mint
`-2.json`, then `-3.json`, then `-4.json` forever. It does not: pass 2 skips any
address already present in `osm_addr_slugs`
(`scripts/migrate_ffm_to_records.py:199-202`), which is rebuilt from disk at the
top of each run. Prove it rather than trusting it — run the migration twice and
confirm the record count is unchanged:

```bash
ls data/stolpersteine-records/frankfurt-am-main/*.json | wc -l   # note the number
uv run scripts/migrate_ffm_to_records.py >/dev/null
ls data/stolpersteine-records/frankfurt-am-main/*.json | wc -l   # must match
uv run scripts/migrate_ffm_to_records.py >/dev/null
ls data/stolpersteine-records/frankfurt-am-main/*.json | wc -l   # must still match
```

If the count grows between runs, STOP — the collision handler is not idempotent
and would inflate the archive weekly.

**Note:** these runs write into `data/`. That is the one place in this plan
where that is expected, because the script's normal job is to write records.
Afterwards run `git status --porcelain data/` and, if anything changed, restore
it with `git checkout -- data/` before continuing — this plan must leave the
archive untouched.

### Step 5: Write the consistency checker

Create `scripts/check_records.py`. It is **read-only** — it must never write
into `data/`. It reports, and exits non-zero when it finds problems, so it can
later become a CI gate.

```python
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
from _slug import slugify

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECORDS_DIR = DATA_DIR / "stolpersteine-records"


def load_records(city: str | None) -> list[tuple[Path, dict]]:
    pattern = f"{city}/*.json" if city else "*/*.json"
    out: list[tuple[Path, dict]] = []
    for path in sorted(RECORDS_DIR.glob(pattern)):
        try:
            out.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except json.JSONDecodeError as exc:
            print(f"  CORRUPT {path}: {exc}")
    return out


def addr_key(record: dict) -> tuple[str, str]:
    address = record.get("address") or {}
    return (slugify(address.get("street")), slugify(address.get("house_number")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", help="restrict to one city slug")
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args()

    records = load_records(args.city)
    by_address: dict[tuple[str, str], list[tuple[Path, dict]]] = collections.defaultdict(list)
    for path, record in records:
        by_address[addr_key(record)].append((path, record))

    anonymous = [(p, r) for p, r in records if not (r.get("person") or {}).get("name")]
    orphan_bios = [
        (p, r) for p, r in anonymous if r.get("biographies")
    ]
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
        print(f"anonymous (person.name is null):    {report['anonymous_records']}")
        print(f"biographies stranded on anonymous:  {report['biographies_on_anonymous_records']}")
        print(f"records without coordinates:        {report['records_without_coords']}")
        print(f"addresses split anon+named:         {report['split_locations']}")
        for key, anon, named in split_locations[:20]:
            print(f"  {key[0]} {key[1]}\n     anon:  {anon}\n     named: {named}")
        if len(split_locations) > 20:
            print(f"  ... and {len(split_locations) - 20} more")

    return 1 if split_locations else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Verify**: `uv run scripts/check_records.py` → prints the summary. Expected
values at commit `a44900bf`, which you should confirm:

```
records:                            2868
anonymous (person.name is null):    528
biographies stranded on anonymous:  521
records without coordinates:        360
addresses split anon+named:         463
```

If your numbers differ, the archive has changed since this plan was written —
record the new numbers in the report rather than forcing the old ones.

### Step 6: Test the checker

Create `tests/test_check_records.py` using `tmp_path` fixtures only — never the
real archive:

```python
"""Tests for the record consistency checker."""

import json

from tests.conftest import load_script

check = load_script("check_records_mod", "scripts/check_records.py")


def _record(name, street, house, bios=0):
    return {
        "id": f"frankfurt-am-main/{street}-{house}",
        "person": {"name": name},
        "address": {"street": street, "house_number": house},
        "coords": [50.1, 8.6],
        "biographies": [{"text": "x"} for _ in range(bios)],
        "images": [],
        "enrichers": {},
    }


def test_addr_key_folds_accents_consistently():
    a = check.addr_key(_record("X", "Linnéstraße", "27"))
    b = check.addr_key(_record("Y", "Linnestrasse", "27"))
    assert a == b


def test_addr_key_handles_missing_address():
    assert check.addr_key({"address": {}}) == ("", "")
    assert check.addr_key({}) == ("", "")


def test_load_records_reads_city_dir(tmp_path, monkeypatch):
    city = tmp_path / "testcity"
    city.mkdir()
    (city / "a.json").write_text(
        json.dumps(_record("Anna Muster", "Teststraße", "1")), encoding="utf-8"
    )
    monkeypatch.setattr(check, "RECORDS_DIR", tmp_path)
    records = check.load_records("testcity")
    assert len(records) == 1
    assert records[0][1]["person"]["name"] == "Anna Muster"


def test_load_records_survives_corrupt_json(tmp_path, monkeypatch, capsys):
    city = tmp_path / "testcity"
    city.mkdir()
    (city / "bad.json").write_text("{not json", encoding="utf-8")
    (city / "good.json").write_text(
        json.dumps(_record("Anna Muster", "Teststraße", "1")), encoding="utf-8"
    )
    monkeypatch.setattr(check, "RECORDS_DIR", tmp_path)
    records = check.load_records("testcity")
    assert len(records) == 1
    assert "CORRUPT" in capsys.readouterr().out
```

**Verify**: `uv run pytest -q` → exit 0, all tests pass including the new ones.

### Step 7: Write the findings report

Create `plans/004-findings.md` containing:

1. The exact checker output from step 5 (paste it verbatim).
2. `uv run scripts/check_records.py --json > /tmp/records.json` output
   summarised: how many split locations, and the full list of affected filename
   pairs.
3. The count of records whose filename would change under the unified slugify.
   Compute it read-only:

```bash
uv run python3 - <<'EOF'
import json, sys, pathlib
sys.path.insert(0, 'scripts')
from _slug import slugify
root = pathlib.Path('data/stolpersteine-records')
changed = []
for p in sorted(root.glob('*/*.json')):
    rec = json.loads(p.read_text(encoding='utf-8'))
    a = rec.get('address') or {}
    if not (a.get('street') and a.get('house_number')):
        continue
    expected_prefix = f"{slugify(a['street'])}-{slugify(a['house_number'])}"
    if not p.stem.startswith(expected_prefix):
        changed.append((p.name, expected_prefix))
print(len(changed), "records whose filename disagrees with the unified slug")
for name, exp in changed[:30]:
    print("  ", name, "->", exp)
EOF
```

4. A short recommendation section answering: which records should be merged,
   which should be renamed, and whether the merge should run as a one-off script
   or be folded into `migrate_ffm_to_records.py`. State open questions rather
   than guessing.

**Verify**: `plans/004-findings.md` exists and contains the checker output and
the filename-disagreement count.

## Test plan

New tests: `tests/test_slug.py` (12 parametrized cases plus 2 property-style
tests) and `tests/test_check_records.py` (4 tests). Model both on the structure
of `tests/test_merge.py` from plan 001 — plain pytest functions, `tmp_path` for
any filesystem work, no reliance on real archive files.

Cases covered: umlaut folding, accent folding, empty/`None` input, path
separators and dot-segments never surviving, agreement with the OSM script's
slugs, address-key normalization, corrupt-JSON tolerance.

Verification: `uv run pytest -q` → all pass.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `uv run pytest -q` exits 0
- [ ] `uv run pytest tests/test_slug.py tests/test_check_records.py -q` exits 0
- [ ] `scripts/_slug.py` exists and `grep -n "^def slugify" scripts/migrate_ffm_to_records.py` returns **no matches**
- [ ] `uv run scripts/check_records.py` runs and prints all five summary lines
- [ ] `grep -n "COLLISION" scripts/migrate_ffm_to_records.py` returns exactly one match
- [ ] `plans/004-findings.md` exists and contains the checker output
- [ ] `git status --porcelain data/` returns **no output** — not one record was
      modified. (Step 4's idempotence runs write into `data/`; restore with
      `git checkout -- data/` before checking this box.)
- [ ] `git status --porcelain` lists only: `scripts/_slug.py`, `scripts/check_records.py`, `scripts/migrate_ffm_to_records.py`, `tests/test_slug.py`, `tests/test_check_records.py`, `plans/004-findings.md`, `plans/README.md`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The code at the locations quoted in "Current state" doesn't match the live
  files (the codebase drifted since this plan was written).
- `test_slugify_matches_osm_script_for_committed_names` cannot be made to pass
  without changing `scripts/fetch_osm_stolpersteine.py` — that file is out of
  scope because its slugs name 727 committed records.
- The checker reports numbers wildly different from the expected values in step
  5 (e.g. zero split locations, or more than 3,000 records). Something is
  reading the wrong directory; report rather than adjusting the expectation.
- You find yourself about to rename, merge, or delete any file under
  `data/stolpersteine-records/`. That is explicitly not this plan. Stop.
- You conclude the fix requires changing `fetch_initiative_stolpersteine.py`'s
  matching tiers. Record it in the findings report as a recommendation instead.

## Maintenance notes

- **The follow-up this plan enables**: merging the 463 split locations and
  re-attaching 521 stranded biographies. That work rewrites committed records
  and needs its own plan, scoped by `plans/004-findings.md`. It should be a
  one-off, reviewable, idempotent script — not a change to the weekly cron.
- After step 3, `migrate_ffm_to_records.py` produces *different* filenames than
  the committed ones for accented streets. Until the merge follow-up runs, the
  next cron will create new records alongside the old ones. If that is
  unacceptable before the merge lands, hold this plan's step 3 and 4 back — but
  say so explicitly; the divergence is otherwise permanent.
- `scripts/check_records.py` is deliberately **not** wired into
  `.github/workflows/archive.yml` yet. It exits 1 today (463 split locations),
  so adding it as a gate would immediately break the cron. Wire it in only after
  the merge follow-up brings the count to zero.
- Three scripts still carry their own `slugify` (`archive.py`,
  `build_stolpersteine.py`, `fetch_osm_stolpersteine.py`). That is intentional
  here — each names a set of already-committed files. Consolidating them is a
  rename migration, not a refactor.
- A reviewer should confirm the diff touches zero files under `data/`.
