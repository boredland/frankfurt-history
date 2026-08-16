# Plan 004 findings — Stolpersteine record fragmentation

Produced by executing `plans/004-record-identity-audit.md` against commit
`a44900bf` on 2026-08-16. Read-only measurement; no record was modified.

## Checker output

`uv run scripts/check_records.py` (exit code 1):

```
records:                            2868
corrupt files (skipped):            0
anonymous (person.name is null):    528
biographies stranded on anonymous:  521
records without coordinates:        360
addresses split anon+named:         468
```

**Correction to the plan's expected numbers.** The plan predicted
`addresses split anon+named: 463`. The real figure is **468**. The plan's
estimate came from an ad-hoc key of raw lowercased street + raw house number;
`check_records.py` keys on the *slugified* address, which correctly merges
spelling variants of the same street that the raw key kept apart. Verified by
computing both keys over the same data: raw → 463, slugified → 467. A further
address (`Loënstraße 9`) joined the count once `ë` was folded correctly (see
below), giving **468**. The checker is the more accurate of the three; 468 is the
number to work from. Every other predicted value (2868 / 528 / 521 / 360)
matched exactly.

## Shape of the fragmentation

Split-address group sizes (records sharing one address where at least one is
anonymous and at least one is named):

| records at the address | count of addresses |
|---|---|
| 2 | 195 |
| 3 | 94 |
| 4 | 68 |
| 5 | 53 |
| 6 | 31 |
| 7 | 10 |
| 8 | 4 |
| 9 | 5 |
| 10 | 2 |
| 11 | 1 |
| 12 | 2 |
| 13 | 1 |
| 22 | 1 |

**No address holds more than one anonymous record.** Verified across the *whole*
dataset, not just the split groups: zero addresses have two or more anonymous
records, whether or not a named record exists there. This is the single most
useful fact for the merge follow-up — the anonymous location-level record is
always unique per address, so the merge is one-anonymous-to-many-named, never
many-to-many.

Full machine-readable detail: `uv run scripts/check_records.py --json`.

## Filename disagreement under the unified slug

After pointing `scripts/migrate_ffm_to_records.py` at `scripts/_slug.py`, only
**one** committed record's filename disagrees with the slug the pipeline would
now generate:

```
2 records whose filename disagrees with the unified slug
   linn-strasse-27.json -> linnestrasse-27
   lo-nstrasse-9.json   -> loenstrasse-9
```

The second was found only after adversarial review of this commit: the first
version of `scripts/_slug.py` carried a hand-written fold table that had no
entry for `ë`, so `Loënstraße` slugified to the mangled `lo-nstrasse` — the
letter was dropped, not folded. `slugify` now normalises with NFC, expands the
German umlauts to digraphs, then strips remaining diacritics via NFKD, which
covers `ë`, `ł`, `š`, `ž`, `ć`, `ø` and the rest of the Latin range without an
ever-growing table. `tests/test_slug.py` asserts equivalence with
`fetch_osm_stolpersteine.py` across **all 3,011** distinct street, house-number,
district and person strings in the archive, with `Loënstraße` as the single
documented divergence.

`lo-nstrasse-9.json` holds 1 biography with `person.name: null`, while
`loenstrasse-9-alice-bendheim.json` and `loenstrasse-9-emmy-bendheim.json` hold
the names — the same split-record pattern as Linnéstraße 27.

This is the case that motivated the plan. `linn-strasse-27.json` currently holds
1 biography and 3 images with `person.name: null`, while
`linnestrasse-27-wilhelm-adam-hugo.json` holds the victim's name and zero
biographies — one physical stone, split across two files by a slug divergence.

The blast radius of the slug unification is therefore **two filenames**, not
hundreds. Verified separately that the new `slugify` still reproduces every
other committed filename once the `marker_type` prefix and the `-2` dedup
suffix are accounted for (0 unexplained of 2,868). That was the main open risk when the plan was written and it is now
closed.

## Idempotence

Confirmed empirically. `scripts/migrate_ffm_to_records.py` was run three times
in succession with the new collision guard in place:

```
before:     2868 records
after run1: 2868
after run2: 2868
after run3: 2868
```

Pass 2 reported `created 0 … 793 skipped — already in OSM or no addr` on every
run. The collision guard cannot inflate the archive weekly, because pass 2
skips any address already present in `osm_addr_slugs`, which is rebuilt from
disk at the top of each run.

The runs did rewrite 667 files, but the diff is confined to
`enrichers.frankfurt_de.fetched_at` timestamps — no record content changed.
`data/` was restored with `git checkout -- data/` afterwards and verified
pristine (`git status --porcelain data/` → empty, 2868 files).

## Recommendation for the merge follow-up

Scope, in the order I would do it:

1. **Rename the two divergent files.** `linn-strasse-27.json` →
   `linnestrasse-27.json` and `lo-nstrasse-9.json` → `loenstrasse-9.json`.
   Trivial, and it stops the next cron creating a third record for those stones.
2. **Merge anonymous location records into their named siblings.** For each of
   the 468 split addresses: move `biographies` and `images` from the anonymous
   record onto the named records at that address, then delete the anonymous
   record. Because no address has more than one anonymous record, the source is
   always unambiguous.
3. **Decide the attribution rule before writing any code.** This is the open
   question, and it is not a technical one. When an anonymous location record
   carries 1 biography and the address has 3 named stones, which person does
   that biography belong to? Options:
   - attach to all named records at the address (duplicates text, never wrong);
   - attach only when `commemorates` names exactly one person;
   - use the biography's own first-line name extraction
     (`extract_names_from_bio_text` already exists in
     `scripts/migrate_ffm_to_records.py`) and attach by name match, leaving
     unmatched ones on a location record.

   For a memorial archive I would default to the **third**, falling back to
   leaving the biography on a location-level record rather than guessing. A
   biography attached to the wrong victim is worse than one attached to no
   victim.
4. **Run as a one-off reviewable script, not in the cron.** The merge rewrites
   committed records; it should produce a diff a human reads once, not run
   weekly.
5. **Only then wire `check_records.py` into CI.** It exits 1 today; it becomes a
   useful gate once the count reaches zero.

## Open questions for the maintainer

- The attribution rule in item 3 — this needs a human decision.
- The 360 records with no coordinates: should they be geocoded from their
  address, or surfaced in a non-map view? They are currently invisible on the
  site.
- Three scripts still carry their own `slugify` (`archive.py`,
  `build_stolpersteine.py`, `fetch_osm_stolpersteine.py`). Each names
  already-committed files, so unifying them is a rename migration. Worth doing
  only alongside the merge above.
