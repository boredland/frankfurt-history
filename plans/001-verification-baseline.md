# Plan 001: Establish a runnable verification baseline (pytest + typecheck)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat a44900bf..HEAD -- pyproject.toml app/package.json .github/workflows/ scripts/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `a44900bf`, 2026-08-16

## Why this matters

This repository has **zero automated tests** and no Python linter or test
runner. The data pipeline that produces a public memorial archive about
Holocaust victims has no way to detect a regression except by a human noticing
a wrong name on the live site. Plans 004 and 005 both rewrite data-transform
logic; without a test harness they cannot be verified, only hoped about. This
plan adds the harness and pins current behaviour with characterization tests,
so that later plans have a pass/fail signal instead of a judgment call.

This plan deliberately does **not** change any pipeline behaviour. Its tests
record what the code does *today*, including behaviour that plan 005 will later
declare a bug. That is intentional: a characterization test that fails after a
deliberate fix is the signal that the fix took effect.

## Current state

Relevant files:

- `pyproject.toml` — Python project manifest. No `[dependency-groups]`, no test
  config, no linter. Full current contents:

```toml
[project]
name = "frankfurt-history"
version = "0.1.0"
description = "Add your description here"
requires-python = ">=3.12"
dependencies = [
    "beautifulsoup4>=4.14.3",
    "boto3>=1.42.96",
    "httpx>=0.28.1",
    "pdfplumber>=0.11.0",
]
```

- `scripts/merge.py` — merges `data/` + `overrides/` into `content/`. Contains
  `parse_frontmatter`, `serialize_frontmatter`, `clean_body`, `merge_file`.
  Module-level constants (`merge.py:22-26`):

```python
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OVERRIDES_DIR = Path(__file__).resolve().parent.parent / "overrides"
CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"

STRUCTURAL_FIELDS = {"coordinates", "categories", "filters", "id"}
```

- `scripts/geojson.py` — reads merged content, emits GeoJSON. Contains
  `parse_frontmatter` (a *different* implementation from merge.py's) and
  `parse_yaml_list`.
- `.github/workflows/validate.yml` — the only CI that checks data. Runs
  `uv run scripts/merge.py` then an inline Python bbox assertion. Lines 14-19:

```yaml
      - uses: actions/checkout@v7

      - uses: astral-sh/setup-uv@v8.2.0

      - name: Merge data + overrides
        run: uv run scripts/merge.py
```

- `app/package.json` — scripts block (lines 5-15):

```json
  "scripts": {
    "build:data": "cd .. && uv run python3 scripts/merge.py && uv run python3 scripts/geojson.py && uv run python3 scripts/precache_routes.py",
    "dev": "bun run build:data && vite dev",
    "build": "bun run build:data && vite build",
    "start": "vite preview",
    "deploy": "bun run build && wrangler deploy",
    "typecheck": "tsc --noEmit",
    "lint": "biome check src/",
    "lint:fix": "biome check --write src/",
    "check": "bun run typecheck && bun run lint"
  },
```

**Repo conventions you must match:**

- Python: 4-space indent, type hints on function signatures, module-level
  `SCREAMING_CASE` constants, `pathlib.Path` (never `os.path`), f-strings.
  Docstrings are triple-quoted one-liners or short paragraphs. See
  `scripts/fetch_osm_stolpersteine.py:1-20` for the house docstring style.
- Package manager is **`uv`**, never `pip` and never `python -m venv`.
- Commit messages are Conventional Commits. Real examples from `git log`:
  `feat: add Stolpersteine records pipeline and Frankfurt baseline`,
  `fix: refine paragraph joining to handle abbreviations and digit fragments`,
  `ci: pin setup-uv to v8.2.0 (no moving v8 major tag exists)`.
- The `data/` directory is a committed archive of ~10,300 files. **Never**
  modify anything under `data/`. Tests must use fixtures they create in a
  `tmp_path`, not real archive files.

**Important environment fact:** `app/node_modules` is NOT installed in a fresh
checkout, so `bun run typecheck` and `bun run lint` fail with
`tsc: command not found` until `bun install` runs. That is why step 4 adds the
install step to CI.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Add Python dev dep | `uv add --dev pytest` | exit 0, updates `pyproject.toml` + `uv.lock` |
| Run Python tests | `uv run pytest -q` | exit 0, all tests pass |
| Run one test file | `uv run pytest tests/test_merge.py -q` | exit 0 |
| Install JS deps | `cd app && bun install` | exit 0, creates `app/node_modules` |
| Typecheck | `cd app && bun run typecheck` | exit 0, no errors |
| Lint | `cd app && bun run lint` | exit 0 |

## Scope

**In scope** (the only files you should create or modify):

- `pyproject.toml` (modify — add dev dependency group + pytest config)
- `uv.lock` (will be regenerated by `uv add`; commit the result)
- `tests/__init__.py` (create, empty)
- `tests/conftest.py` (create)
- `tests/test_merge.py` (create)
- `tests/test_geojson.py` (create)
- `.github/workflows/validate.yml` (modify — add a test job)

**Out of scope** (do NOT touch, even though they look related):

- `scripts/merge.py`, `scripts/geojson.py`, and every other file under
  `scripts/` — this plan adds tests only. Changing behaviour here would make
  the characterization tests meaningless. Plan 005 changes `merge.py`.
- Anything under `data/`, `overrides/`, or `content/` — `data/` is the
  committed archive, `content/` is a gitignored build artifact.
- `app/src/**` — no TypeScript tests in this plan. Adding a JS test runner is a
  separate decision; this plan only makes the *existing* `typecheck`/`lint`
  scripts actually run in CI.
- `.github/workflows/archive.yml` — the cron pipeline. Do not touch.

## Git workflow

- Branch: `advisor/001-verification-baseline`
- One commit per step is fine; message style is Conventional Commits, e.g.
  `test: add characterization tests for merge and geojson frontmatter parsing`
  and `ci: run pytest and app typecheck in validate workflow`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add pytest as a dev dependency

Run:

```bash
uv add --dev pytest
```

Then add pytest configuration to `pyproject.toml` by appending this block at
the end of the file (keep the existing `[project]` table unchanged):

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

The `pythonpath = ["."]` entry lets tests import the pipeline modules from the
repo root without an installed package.

**Verify**: `uv run pytest --version` → prints a pytest version, exit 0.

### Step 2: Create the test package and a module-loading fixture

The pipeline scripts are standalone scripts under `scripts/`, not an importable
package, and `scripts/` has no `__init__.py`. Load them by file path.

Create `tests/__init__.py` as an empty file.

Create `tests/conftest.py`:

```python
"""Shared fixtures: load the standalone pipeline scripts as importable modules."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_script(name: str, relative_path: str) -> ModuleType:
    """Import a standalone script from scripts/ as a module."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def merge_mod() -> ModuleType:
    return load_script("merge_script", "scripts/merge.py")


@pytest.fixture(scope="session")
def geojson_mod() -> ModuleType:
    return load_script("geojson_script", "scripts/geojson.py")
```

**Verify**: `uv run pytest -q` → exit 0, collects 0 tests, no import errors.

### Step 3: Write characterization tests for `merge.py`

Create `tests/test_merge.py`. These tests pin **current** behaviour. Two of
them assert behaviour that is a known defect; they are marked so with a
comment, and plan 005 will update them.

```python
"""Characterization tests for scripts/merge.py.

These pin CURRENT behaviour, including known defects. A test marked
KNOWN DEFECT documents behaviour that plan 005 will deliberately change; when
that plan lands, the assertion is expected to be updated, not deleted.
"""


def test_parse_frontmatter_roundtrip_simple(merge_mod):
    text = '---\nid: 42\ntitle: "Hauptwache"\n---\n\nBody text.\n'
    fm, body = merge_mod.parse_frontmatter(text)
    assert fm == {"id": "42", "title": '"Hauptwache"'}
    assert body == "Body text."


def test_parse_frontmatter_no_frontmatter_returns_text_unchanged(merge_mod):
    fm, body = merge_mod.parse_frontmatter("Just a body.\n")
    assert fm == {}
    assert body == "Just a body.\n"


def test_parse_frontmatter_keeps_colon_inside_quoted_title(merge_mod):
    # Real archive content: 17 files under data/de have a colon in the title,
    # e.g. "Novemberpogrome 1938: Ein Wendepunkt der Verfolgungspolitik".
    text = '---\ntitle: "Novemberpogrome 1938: Ein Wendepunkt"\n---\n\nBody.\n'
    fm, _ = merge_mod.parse_frontmatter(text)
    assert fm["title"] == '"Novemberpogrome 1938: Ein Wendepunkt"'


def test_parse_frontmatter_multiline_list_value(merge_mod):
    text = '---\nfilters:\n  - "Schauplätze"\n  - "Theater"\n---\n\nBody.\n'
    fm, _ = merge_mod.parse_frontmatter(text)
    assert "Schauplätze" in fm["filters"]
    assert "Theater" in fm["filters"]


def test_clean_body_strips_leading_title_and_subtitle(merge_mod):
    body = "# Hauptwache\n\n*An der Hauptwache*\n\nEin ganzer Satz zum Ort.\n"
    out = merge_mod.clean_body(body)
    assert "# Hauptwache" not in out
    assert "*An der Hauptwache*" not in out
    assert "Ein ganzer Satz zum Ort." in out


def test_clean_body_preserves_normal_paragraph(merge_mod):
    body = (
        "Dies ist ein vollstaendiger Absatz mit ausreichender Laenge, "
        "der erhalten bleiben muss.\n"
    )
    assert "vollstaendiger Absatz" in merge_mod.clean_body(body)


def test_clean_body_drops_short_final_fragment_KNOWN_DEFECT(merge_mod):
    # KNOWN DEFECT (plan 005): a short standalone line before an image or at the
    # end of the body is deleted. Verified against real content:
    # data/de/frankfurt-stories/2205-hauptwache.md loses "Frankfurter Mobilitätsorte".
    body = (
        "# Hauptwache\n\n"
        "*An der Hauptwache*\n\n"
        "Frankfurter Mobilitätsorte\n\n"
        "![Bild](../../images/x.jpg)\n"
    )
    out = merge_mod.clean_body(body)
    assert "Frankfurter Mobilitätsorte" not in out


def test_clean_body_renames_links_heading_to_sources(merge_mod):
    body = "Ein ausreichend langer Absatz als Kontext hier.\n\n## Links\n"
    assert "## Sources" in merge_mod.clean_body(body)


def test_merge_file_override_frontmatter_wins(merge_mod, tmp_path):
    base = tmp_path / "base.md"
    base.write_text(
        '---\nid: 1\ntitle: "Alt"\ncoordinates: [50.1, 8.6]\n---\n\n'
        "Ein ausreichend langer Basistext als Inhalt.\n",
        encoding="utf-8",
    )
    override = tmp_path / "override.md"
    override.write_text('---\ntitle: "Neu"\n---\n', encoding="utf-8")

    out = merge_mod.merge_file(base, override)
    assert '"Neu"' in out
    assert '"Alt"' not in out
    assert "Basistext" in out  # empty override body keeps the base body


def test_merge_file_override_null_deletes_field(merge_mod, tmp_path):
    base = tmp_path / "base.md"
    base.write_text(
        '---\nid: 1\ntitle: "Alt"\nsubtitle: "Weg damit"\n---\n\n'
        "Ein ausreichend langer Basistext als Inhalt.\n",
        encoding="utf-8",
    )
    override = tmp_path / "override.md"
    override.write_text("---\nsubtitle: null\n---\n", encoding="utf-8")

    out = merge_mod.merge_file(base, override)
    assert "subtitle" not in out


def test_merge_file_override_body_replaces_base_body(merge_mod, tmp_path):
    base = tmp_path / "base.md"
    base.write_text(
        '---\nid: 1\ntitle: "Alt"\n---\n\nAlter Text mit genuegend Laenge hier.\n',
        encoding="utf-8",
    )
    override = tmp_path / "override.md"
    override.write_text(
        '---\ntitle: "Alt"\n---\n\nNeuer Text mit genuegend Laenge hier.\n',
        encoding="utf-8",
    )

    out = merge_mod.merge_file(base, override)
    assert "Neuer Text" in out
    assert "Alter Text" not in out


def test_merge_file_override_only_no_base_file(merge_mod, tmp_path):
    """PLAN.md documents: 'data/ file deleted by API -> override-only POI still appears'."""
    missing = tmp_path / "does-not-exist.md"
    override = tmp_path / "override.md"
    override.write_text(
        '---\nid: 99\ntitle: "Nur Override"\n---\n\n'
        "Ein ausreichend langer Text als Inhalt hier.\n",
        encoding="utf-8",
    )

    out = merge_mod.merge_file(missing, override)
    assert '"Nur Override"' in out
```

**Verify**: `uv run pytest tests/test_merge.py -q` → exit 0, 12 passed.

If any test fails, do NOT change `scripts/merge.py`. A failure means the
assertion does not match current behaviour — correct the *assertion* to match
what the code actually does, and note the correction in your final report.
These are characterization tests: they describe reality, not an ideal.

### Step 4: Write characterization tests for `geojson.py` coordinate filtering

Create `tests/test_geojson.py`. Note `geojson.py`'s `parse_frontmatter` takes a
**Path**, unlike `merge.py`'s which takes a string.

```python
"""Characterization tests for scripts/geojson.py frontmatter and coordinate handling."""


def _write_poi(tmp_path, name, frontmatter):
    path = tmp_path / name
    path.write_text(f"---\n{frontmatter}\n---\n\nBody.\n", encoding="utf-8")
    return path


def test_parse_frontmatter_parses_coordinate_list_as_floats(geojson_mod, tmp_path):
    poi = _write_poi(tmp_path, "0001-x.md", 'id: 1\ncoordinates: [50.1105, 8.6821]')
    fm = geojson_mod.parse_frontmatter(poi)
    assert fm["coordinates"] == [50.1105, 8.6821]


def test_parse_frontmatter_empty_coordinate_list(geojson_mod, tmp_path):
    poi = _write_poi(tmp_path, "0002-x.md", "id: 2\ncoordinates: []")
    assert geojson_mod.parse_frontmatter(poi)["coordinates"] == []


def test_parse_frontmatter_non_numeric_coords_fall_back_to_strings(geojson_mod, tmp_path):
    poi = _write_poi(tmp_path, "0003-x.md", 'id: 3\ncoordinates: ["nord", "ost"]')
    assert geojson_mod.parse_frontmatter(poi)["coordinates"] == ["nord", "ost"]


def test_parse_yaml_list_reads_block_list(geojson_mod, tmp_path):
    poi = _write_poi(
        tmp_path, "0004-x.md", 'id: 4\nfilters:\n  - "Schauplätze"\n  - "Theater"'
    )
    assert geojson_mod.parse_yaml_list(poi, "filters") == ["Schauplätze", "Theater"]


def test_parse_yaml_list_missing_key_returns_empty(geojson_mod, tmp_path):
    poi = _write_poi(tmp_path, "0005-x.md", "id: 5")
    assert geojson_mod.parse_yaml_list(poi, "filters") == []


# The Frankfurt bounding box enforced by geojson.py is
# 49.5 < lat < 50.5 and 8.0 < lng < 9.5; a POI outside it prints "SKIP ..."
# and is excluded. validate.yml enforces a TIGHTER box (49.9..50.3 lat,
# 8.3..9.0 lng). The mismatch is real and intentionally recorded here.
#
# These two tests drive the REAL filter through build_theme(). Do NOT rewrite
# them to assert the bbox arithmetic inline (`assert 49.5 < lat < 50.5`) —
# that tests nothing and would still pass if geojson.py regressed.
#
# Verified signature at commit a44900bf:
#   build_theme(theme_dir: Path, addresses=None, en_dir=None)
#       -> tuple[dict | None, dict | None]   # (theme_meta, geojson)
# It returns (None, None) when the directory has no _index.md, so the fixture
# must create one.
def _write_theme(tmp_path):
    theme = tmp_path / "testtheme"
    theme.mkdir()
    (theme / "_index.md").write_text(
        '---\nid: 99\ntitle: "Testtheme"\nshort_title: "Test"\n---\n', encoding="utf-8"
    )
    return theme


def test_bbox_keeps_frankfurt_centre_poi(geojson_mod, tmp_path):
    theme = _write_theme(tmp_path)
    _write_poi(theme, "0001-mitte.md", 'id: 1\ntitle: "Mitte"\ncoordinates: [50.1105, 8.6821]')
    _meta, gj = geojson_mod.build_theme(theme)
    assert [f["properties"]["slug"] for f in gj["features"]] == ["0001-mitte"]


def test_bbox_rejects_utm_style_bad_coordinate(geojson_mod, tmp_path, capsys):
    # BAD_COORDINATES.md documents upstream POIs carrying UTM values in
    # WGS84 fields, e.g. [50.1233304, 866923].
    theme = _write_theme(tmp_path)
    _write_poi(theme, "0002-utm.md", 'id: 2\ntitle: "UTM"\ncoordinates: [50.1233304, 866923]')
    _meta, gj = geojson_mod.build_theme(theme)
    assert gj["features"] == []
    assert "SKIP" in capsys.readouterr().out
```

**Verify**: `uv run pytest -q` → exit 0, 19 passed (12 from merge + 7 from geojson).

The `build_theme` signature and both assertions above were executed against the
real `scripts/geojson.py` at commit `a44900bf` before this plan was written, so
they should pass as-is. Confirm the function still exists first:

```bash
grep -n "^def build_theme" scripts/geojson.py
```

If it has been renamed or its return shape changed, adapt the two calls to the
real signature — but **do not** fall back to asserting the bbox arithmetic
inline. If the filter is no longer reachable without running the whole script,
mark both tests `@pytest.mark.skip(reason="coordinate filter not independently callable")`
and say so in your report: a skipped honest test beats a passing vacuous one.

If any other function signature differs from what these tests assume (for
example `parse_yaml_list` takes different arguments), read the real signature in
`scripts/geojson.py` and adapt the test call. Do not change `geojson.py`.

### Step 5: Wire tests and the app check into CI

Modify `.github/workflows/validate.yml`. The existing job is named
`check-coordinates` (the *workflow* is named `Validate Data`) — keep that job
exactly as it is and **add** two more. Append this to the `jobs:` mapping,
matching the existing file's 2-space indentation:

```yaml
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: astral-sh/setup-uv@v8.2.0

      - name: Run Python tests
        run: uv run pytest -q

  app-check:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: app
    steps:
      - uses: actions/checkout@v7

      - uses: oven-sh/setup-bun@v2

      - name: Install dependencies
        run: bun install --frozen-lockfile

      - name: Typecheck and lint
        run: bun run check
```

Also extend the workflow's path filters so code changes trigger it, not only
data changes. The current trigger block is:

```yaml
on:
  push:
    branches: [main]
    paths: [data/**, overrides/**, content/**]
  pull_request:
    paths: [data/**, overrides/**, content/**]
```

Add `scripts/**`, `app/**`, `archive.py`, `tests/**`, and `pyproject.toml` to
**both** `paths` lists.

**Verify**:
- `uv run pytest -q` → exit 0.
- `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/validate.yml')); print('ok')"`
  → prints `ok`. (If PyYAML is unavailable, run
  `uv run --with pyyaml python3 -c "..."` instead.)

### Step 6: Confirm the app check actually passes

The `app-check` CI job is only useful if it passes today. Verify locally:

```bash
cd app && bun install && bun run check
```

**Verify**: exit 0 with no type errors and no lint errors.

If `bun run check` reports pre-existing type or lint errors, this is a STOP
condition — report the exact errors. Do NOT fix them and do NOT silence them
by weakening `app/biome.json` or `app/tsconfig.json`; a pre-existing failure is
information the operator needs before this job can be made blocking.

## Test plan

All tests are new; there is no existing test to model on. Structure both files
as plain pytest functions using the `merge_mod` / `geojson_mod` fixtures from
`tests/conftest.py`.

Coverage this plan adds:

- `merge.py`: frontmatter parse (simple, absent, colon-in-title, multi-line
  list), `clean_body` (title/subtitle strip, paragraph preservation, the known
  short-fragment defect, `## Links` rename), `merge_file` (frontmatter
  override, `null` deletion, body replacement, override-only file).
- `geojson.py`: coordinate list parsing (floats, empty, non-numeric fallback),
  `parse_yaml_list` (present, missing), bounding-box accept/reject.

Verification: `uv run pytest -q` → all pass, 19 tests.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `uv run pytest -q` exits 0 with at least 19 tests passing
- [ ] `uv run pytest tests/test_merge.py -q` exits 0
- [ ] `uv run pytest tests/test_geojson.py -q` exits 0
- [ ] `cd app && bun run check` exits 0
- [ ] `pyproject.toml` contains a `[tool.pytest.ini_options]` section
- [ ] `.github/workflows/validate.yml` contains jobs named `test` and `app-check`
- [ ] `git status --porcelain data/ overrides/` returns **no output** (the archive is untouched)
- [ ] `git status --porcelain scripts/ archive.py` returns **no output** (no pipeline behaviour changed)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The code at the locations quoted in "Current state" doesn't match the live
  files (the codebase drifted since this plan was written).
- `cd app && bun run check` fails on code you did not touch — report the exact
  errors rather than fixing or suppressing them.
- A characterization test cannot be made to pass without editing a file under
  `scripts/` — that is out of scope; report the mismatch instead.
- `uv add --dev pytest` fails to resolve, or `uv.lock` changes in ways
  unrelated to pytest.
- You conclude a test would need a real file from `data/` to work. It must not;
  use `tmp_path` fixtures.

## Maintenance notes

- These are **characterization** tests, not specifications. Two assertions
  (`test_clean_body_drops_short_final_fragment_KNOWN_DEFECT` and the tighter-vs-
  looser bbox comment in `test_geojson.py`) document behaviour that is wrong on
  purpose. Plan 005 changes the first one; when it does, the assertion should be
  inverted, not deleted.
- The bounding box is defined in **two** places with **different** values:
  `scripts/geojson.py` uses `49.5..50.5 / 8.0..9.5`, while
  `.github/workflows/validate.yml` uses `49.9..50.3 / 8.3..9.0`. A POI can pass
  one and fail the other. Consolidating them is deliberately deferred — it is a
  behaviour change, and this plan changes no behaviour.
- A reviewer should check that no file under `data/`, `overrides/`, or
  `scripts/` appears in the diff.
- Deferred out of this plan: any JavaScript test runner (vitest). The app has no
  tests; adding a runner is a separate decision. This plan only ensures the
  already-configured `typecheck` and `lint` scripts run in CI.
