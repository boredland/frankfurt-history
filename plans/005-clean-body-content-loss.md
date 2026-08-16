# Plan 005: Stop `clean_body` from silently deleting article content

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat a44900bf..HEAD -- scripts/merge.py tests/test_merge.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (changes rendered output for every article)
- **Depends on**: plans/001-verification-baseline.md (needs the characterization tests it adds)
- **Category**: bug
- **Planned at**: commit `a44900bf`, 2026-08-16

## Why this matters

`clean_body()` in `scripts/merge.py` rewrites every article body on its way from
`data/` into `content/`. One of its heuristics deletes any block shorter than 30
characters that does not end in `.` or `:` when that block is last or sits
before an image or heading. It was written to strip junk fragments, but it also
deletes real content.

Measured against the live archive: **22 legitimate content lines across 28
files** are silently removed. Confirmed examples:

| Deleted line | File |
|---|---|
| `Frankfurter Mobilitätsorte` | `data/de/frankfurt-stories/2205-hauptwache.md` |
| `Städtische Bühnen` | `data/de/feministisches-frankfurt/2163-aleida-montijn-1908-1989.md` |
| `Dr. Hoch’s Konservatorium` | `data/de/feministisches-frankfurt/2170-louise-héritte-viardot-1841-1918.md` |
| `Mainzer Landstraße` | `data/de/feministisches-frankfurt/2174-rosy-geiger-kullmann-1886-1964.md` |
| `Leverkuser Straße 9` | `data/de/frankfurt-und-der-ns/2217-wohnhaus-der-familie-levi.md` |
| `Recherche: Jutta Zwilling` | `data/de/frankfurt-und-der-ns/1714-geraubter-ort.md` |
| `125 Jahre FSV (1899-2024)` | `data/de/frankfurt-stories/1583-fanprojekt-des-fsv.md` |

These are venue names, addresses, and a researcher credit — exactly the short,
punctuation-free strings the heuristic targets. `Recherche: Jutta Zwilling` is
an attribution being dropped from a page about Nazi-era property theft. The
deletion is invisible: nothing logs it, and `data/` still holds the original, so
the loss only appears on the rendered site.

After this plan, the heuristic no longer removes content; it is narrowed to the
junk it was actually written for, and the tests from plan 001 are updated to
assert the corrected behaviour.

## Current state

`scripts/merge.py:76` declares the function:

```python
def clean_body(body: str) -> str:
    """Join fragmented paragraphs and replace single newlines with spaces."""
```

The offending block is the last transformation, `scripts/merge.py:216-227`,
verbatim:

```python
    # Final cleanup: strip very short fragments from the end of the blocks
    cleaned_final = []
    for i, block in enumerate(final_blocks):
        is_structural = block.startswith('#') or block.startswith('-') or '![' in block
        # Aggressively strip short fragments that don't end in punctuation
        if not is_structural and len(block) < 30 and not block.endswith('.') and not block.endswith(':') and ': ' not in block:
            # Check if it's followed by a structural element or it's the last block
            is_last = i == len(final_blocks) - 1
            next_is_structural = not is_last and (final_blocks[i+1].startswith('#') or '![' in final_blocks[i+1])
            if is_last or next_is_structural:
                continue 
        cleaned_final.append(block)
```

Note `continue` at line 226 — the block is dropped with no record of it.

Two facts that scope the fix:

- The intended junk this rule targets is already handled **earlier** by a
  separate rule at `scripts/merge.py:113-114`, which drops filename-like blocks:

```python
        # Strip filename-like lines (e.g., kueferstrasse-3)
        if re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)+$', block, re.I) and len(block) < 50:
            continue
```

- Of the 22 dropped lines, 21 are real content. The remaining one,
  `<span class="tab2">K</span>` in
  `data/de/frankfurt-und-der-ns/2233-universitaets-hautklinik.md`, is stray
  markup. The narrowed rule in step 2 keeps it (it contains the letter `K`),
  which is an accepted trade-off — see the note in step 2. The rule still drops
  blocks that are *entirely* markup or whitespace, such as a bare `<br/>`.

**Where this runs.** `clean_body` is called from `merge_file`
(`scripts/merge.py:253`) for every article in both locales, and `merge.py` runs
as the first step of `app/package.json`'s `build:data`, so its output is what
the site renders. `content/` is gitignored — regenerating it is safe and
expected.

**Test file to update.** Plan 001 created `tests/test_merge.py` containing:

```python
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
```

This plan inverts that assertion. If plan 001 has not landed, STOP — see STOP
conditions.

**Repo conventions you must match:**

- Python 3.12+, 4-space indent, type hints, `pathlib.Path`, f-strings.
  `merge.py` itself uses single-quoted strings inside `clean_body` and
  double-quoted elsewhere; match the surrounding lines rather than reformatting.
- Do NOT reformat or restructure the rest of `clean_body`. It is a 156-line pile
  of heuristics; a wholesale rewrite is a different, much riskier change.
- Commit style: Conventional Commits, e.g.
  `fix: stop clean_body deleting short content lines`.
- **Never modify anything under `data/`.**

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run tests | `uv run pytest -q` | exit 0 |
| Run merge tests only | `uv run pytest tests/test_merge.py -q` | exit 0 |
| Rebuild content | `uv run python3 scripts/merge.py` | exit 0, prints per-locale counts |
| Rebuild geojson | `uv run python3 scripts/geojson.py` | exit 0 |

## Scope

**In scope**:

- `scripts/merge.py` (modify — **only** the block at lines 216-227)
- `tests/test_merge.py` (modify — invert the KNOWN DEFECT test, add new cases)

**Out of scope** (do NOT touch, even though they look related):

- The rest of `clean_body` (lines 76-215): the title/subtitle strip, the
  paragraph-joining heuristics, the table interleaving, the `## Links` rename.
  All are separate behaviours with their own risks. Changing them is not this
  plan.
- `parse_frontmatter` / `serialize_frontmatter` — the hand-rolled YAML parser is
  a known separate finding, not this one.
- Anything under `data/` or `overrides/`.
- `content/` and `app/public/data/` — build outputs. You will regenerate them
  for verification; do not commit them (both are gitignored).
- `scripts/geojson.py` — consumes `content/` but needs no change.

## Git workflow

- Branch: `advisor/005-clean-body-content-loss`
- One or two commits; Conventional Commits, e.g.
  `fix: narrow clean_body fragment stripping to markup-only blocks`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Capture the current output as a baseline

Before changing anything, record what the pipeline produces today so you can
diff against it in step 4.

```bash
uv run python3 scripts/merge.py
cp -r content /tmp/content-before
```

**Verify**: `ls /tmp/content-before/de | head` lists theme directories, and
`find /tmp/content-before -name '*.md' | wc -l` prints a non-zero count
(expect roughly 3,500 across both locales plus the flat layout).

### Step 2: Narrow the fragment-stripping rule

Replace the block at `scripts/merge.py:216-227` with a version that only drops
blocks which carry no readable text, and which reports what it dropped:

```python
    # Final cleanup: drop trailing blocks that carry no readable text.
    # Historical note: this rule used to delete ANY block under 30 chars that
    # lacked terminal punctuation, which silently removed real content such as
    # venue names ("Städtische Bühnen"), addresses ("Leverkuser Straße 9") and
    # research credits ("Recherche: Jutta Zwilling"). It is now restricted to
    # blocks that are empty once markup is stripped.
    cleaned_final = []
    dropped_blocks: list[str] = []
    for block in final_blocks:
        is_structural = block.startswith('#') or block.startswith('-') or '![' in block
        if not is_structural and not _has_readable_text(block):
            dropped_blocks.append(block)
            continue
        cleaned_final.append(block)
    if dropped_blocks:
        print(f"    clean_body: dropped {len(dropped_blocks)} markup-only block(s)")
```

Two details that matter:

- The `is_structural` guard is **kept** from the original code. It covers `#`
  headings, `-` prefixed blocks (including a `---` horizontal rule) and image
  blocks. Note it does *not* cover `***` rules or `|---|---|` table separators —
  those contain no alphanumeric character and would still be dropped. That is
  acceptable **only** because no article body in the current archive contains
  one; verified with:

  ```bash
  uv run python3 - <<'EOF'
  import importlib.util, pathlib, re
  spec = importlib.util.spec_from_file_location("m", "scripts/merge.py")
  m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
  hits = 0
  for p in pathlib.Path("data/de").rglob("*.md"):
      _, body = m.parse_frontmatter(p.read_text(encoding="utf-8"))
      for line in body.splitlines():
          if line.strip() in ("---", "***") or re.match(r"^\|[-|: ]+\|$", line.strip()):
              hits += 1
  print(hits, "structural rule lines in article bodies")
  EOF
  ```

  Expected: `0`. If this prints a non-zero number, the archive has gained
  markdown tables or `***` rules since this plan was written — extend
  `is_structural` to cover them before proceeding.
- The drop is reported as a **count**, not one line per block. `clean_body` runs
  over ~3,500 files per build; a per-block `print` would bury the merge output
  in CI and in `bun run dev`.

And add this helper directly above `clean_body` (above line 76):

```python
def _has_readable_text(block: str) -> bool:
    """True when a block contains text beyond HTML markup and punctuation."""
    without_markup = re.sub(r'<[^>]+>', '', block)
    return any(ch.isalnum() for ch in without_markup)
```

Use `str.isalnum()`, **not** a character-range regex such as
`[A-Za-zÀ-ÿ0-9]`. A Latin-1 range silently excludes `Ł`, `Š`, `Ć`, `Ž`, `Œ` and
`ẞ` — exactly the Polish and Czech letters that appear in victim names in this
archive — while wrongly counting `×` and `÷` as letters. `isalnum()` is correct
for the full Unicode range and is shorter.

**Verify**: run

```bash
uv run python3 - <<'EOF'
import importlib.util
spec = importlib.util.spec_from_file_location("m", "scripts/merge.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print(m._has_readable_text("Städtische Bühnen"))            # expect True
print(m._has_readable_text("   "))                          # expect False
print(m._has_readable_text("<br/>"))                        # expect False
print(m._has_readable_text('<span class="tab2">K</span>'))  # expect True
print(m._has_readable_text("Łódź"))                         # expect True
print(m._has_readable_text("Šimon Ćurković"))               # expect True
EOF
```

→ prints `True`, `False`, `False`, `True`, `True`, `True` in that order. These
expected values were checked against this exact helper before the plan was
written. The last two are the reason for `isalnum()` over a Latin-1 regex.

The last one is deliberate and worth understanding before you continue:
stripping the tags from `<span class="tab2">K</span>` leaves `K`, which is a
letter, so the block is **kept**. That is the intended trade-off — this plan
errs toward keeping content. A stray `K` rendering on one article
(`data/de/frankfurt-und-der-ns/2233-universitaets-hautklinik.md`) is a far
smaller harm than deleting an address or a research credit. Do **not** add a
special case to drop it.

### Step 3: Update and extend the tests

In `tests/test_merge.py`, replace
`test_clean_body_drops_short_final_fragment_KNOWN_DEFECT` with an inverted
assertion, and add cases for the other real examples:

```python
def test_clean_body_keeps_short_content_line_before_image(merge_mod):
    # Regression: this line used to be silently deleted.
    # Real case: data/de/frankfurt-stories/2205-hauptwache.md
    body = (
        "# Hauptwache\n\n"
        "*An der Hauptwache*\n\n"
        "Frankfurter Mobilitätsorte\n\n"
        "![Bild](../../images/x.jpg)\n"
    )
    assert "Frankfurter Mobilitätsorte" in merge_mod.clean_body(body)


def test_clean_body_keeps_short_trailing_venue_name(merge_mod):
    # Real case: data/de/feministisches-frankfurt/2163-aleida-montijn-1908-1989.md
    body = "Ein ausreichend langer Absatz als Kontext hier.\n\nStädtische Bühnen\n"
    assert "Städtische Bühnen" in merge_mod.clean_body(body)


def test_clean_body_keeps_short_trailing_address(merge_mod):
    # Real case: data/de/frankfurt-und-der-ns/2217-wohnhaus-der-familie-levi.md
    body = "Ein ausreichend langer Absatz als Kontext hier.\n\nLeverkuser Straße 9\n"
    assert "Leverkuser Straße 9" in merge_mod.clean_body(body)


def test_clean_body_keeps_research_credit(merge_mod):
    # Real case: data/de/frankfurt-und-der-ns/1714-geraubter-ort.md
    body = "Ein ausreichend langer Absatz als Kontext hier.\n\nRecherche: Jutta Zwilling\n"
    assert "Jutta Zwilling" in merge_mod.clean_body(body)


def test_clean_body_drops_whitespace_only_block(merge_mod):
    body = "Ein ausreichend langer Absatz als Kontext hier.\n\n   \n"
    out = merge_mod.clean_body(body)
    assert "Absatz" in out
    assert out.strip().endswith("hier.")
```

Keep every other test in the file unchanged.

**Verify**: `uv run pytest tests/test_merge.py -q` → exit 0, all pass
(16 tests: the 11 retained from plan 001 plus these 5).

### Step 4: Diff the regenerated content against the baseline

```bash
uv run python3 scripts/merge.py
diff -rq /tmp/content-before content | head -40
diff -rq /tmp/content-before content | wc -l
```

Then inspect two of the known-affected files in detail:

```bash
diff /tmp/content-before/de/frankfurt-stories/2205-hauptwache.md \
     content/de/frankfurt-stories/2205-hauptwache.md
diff /tmp/content-before/de/frankfurt-und-der-ns/1714-geraubter-ort.md \
     content/de/frankfurt-und-der-ns/1714-geraubter-ort.md
```

**Verify**: each of those two diffs shows the previously-missing line being
**added back**, and no other change. The repo-wide `diff -rq` count should be
small — on the order of the 28 files measured, not thousands. If hundreds of
files changed, the edit was broader than intended: STOP.

### Step 5: Confirm the downstream build still works

```bash
uv run python3 scripts/geojson.py
```

**Verify**: exit 0, and the final summary prints `Total: 2736 POIs across 7
themes` (or a number within a handful of that — the archive may have moved).
A large drop in POI count means `clean_body` changes broke frontmatter parsing
downstream: STOP.

Optionally render one affected article to confirm it reads correctly:

```bash
cd app && bun run dev
```

then open `/de/frankfurt-stories/2205-hauptwache` and confirm
`Frankfurter Mobilitätsorte` is visible in the article body.

### Step 6: Clean up the baseline copy

```bash
rm -rf /tmp/content-before
```

**Verify**: `git status --porcelain` shows only `scripts/merge.py`,
`tests/test_merge.py`, and `plans/README.md` — `content/` is gitignored and must
not appear.

## Test plan

Modified: `tests/test_merge.py`. One assertion inverted
(`..._KNOWN_DEFECT` → `test_clean_body_keeps_short_content_line_before_image`),
four new regression tests added for the real deleted lines, one new test for the
whitespace-only case that should still be dropped.

Use the existing tests in that file as the structural pattern: plain pytest
functions taking the `merge_mod` fixture from `tests/conftest.py`, no filesystem
access, German content in the fixtures because the real data is German.

Cases: short line before an image; short trailing venue name; short trailing
address; a `Recherche:` credit; whitespace-only block still dropped; plus the
untouched pre-existing tests for title/subtitle stripping, paragraph
preservation and the `## Links` rename.

Verification: `uv run pytest -q` → all pass.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `uv run pytest -q` exits 0
- [ ] `uv run pytest tests/test_merge.py -q` exits 0 with 16 tests
- [ ] `grep -n "KNOWN_DEFECT" tests/test_merge.py` returns **no matches**
- [ ] `grep -n "_has_readable_text" scripts/merge.py` returns the definition and its call
- [ ] `grep -n "len(block) < 30" scripts/merge.py` returns **no matches**
- [ ] `uv run python3 scripts/merge.py && uv run python3 scripts/geojson.py` both exit 0
- [ ] `git status --porcelain data/ overrides/` returns **no output**
- [ ] `git status --porcelain` lists only `scripts/merge.py`, `tests/test_merge.py`, `plans/README.md`
- [ ] Step 4's targeted diffs show the missing lines restored
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `tests/test_merge.py` does not exist, or does not contain
  `test_clean_body_drops_short_final_fragment_KNOWN_DEFECT`. That means plan 001
  has not landed; this plan depends on it. Do not write the tests from scratch —
  execute plan 001 first.
- The code at `scripts/merge.py:216-227` doesn't match the excerpt in "Current
  state" (the file drifted since this plan was written).
- Step 4's repo-wide diff shows more than ~60 changed files. The narrowed rule
  should affect roughly the 28 files measured; a much larger blast radius means
  the edit hit something else.
- Step 5's POI total drops by more than a handful from 2,736.
- You find yourself editing the paragraph-joining or table-interleaving
  heuristics to make a test pass. Those are out of scope; report the interaction
  instead.

## Maintenance notes

- `clean_body` remains a 156-line stack of interacting heuristics operating on
  scraped German prose. This plan fixes the one rule with measured content loss;
  the paragraph-joining rule at lines 189-213 and the table-interleaving rule at
  lines 137-170 are equally heuristic and equally untested. If article rendering
  bugs are reported later, those are the next places to look.
- The dropped-block `print` added in step 2 makes future loss visible in the
  merge log. If it turns out to be noisy in CI, downgrade it to a counter
  printed once at the end — do not remove it silently.
- `content/` is gitignored, so nothing about this change is visible in the repo
  diff beyond the two source files. The user-visible effect only appears after a
  rebuild and redeploy.
- A reviewer should check that the diff touches **only** the final block of
  `clean_body` plus the new helper, and that no file under `data/` moved.
- Deferred out of this plan: replacing the hand-rolled frontmatter parser with a
  real YAML parser, and reviewing the remaining `clean_body` heuristics. Both
  are separate findings.
