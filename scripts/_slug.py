"""Single source of truth for record slug construction.

Historically each pipeline script carried its own copy of ``slugify``. They
disagreed on accented-Latin folding, which split one physical stone across two
record files (e.g. Linnéstraße -> ``linnestrasse`` vs ``linn-strasse``).

This implementation matches scripts/fetch_osm_stolpersteine.py, which already
names the majority of committed records. Changing it renames files on disk —
do not "improve" it without a migration.
"""

import re
import unicodedata

# German umlauts expand to digraphs (ä -> ae); everything else folds to its base
# letter. Order matters only in that the German pairs must be applied before the
# generic NFKD fold below, which would otherwise turn "ä" into "a".
_FOLD = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "æ": "ae", "œ": "oe",
}

_TRANSLATION = str.maketrans(_FOLD)


def slugify(text: str | None) -> str:
    """ASCII kebab-case slug.

    German umlauts expand to digraphs (ä -> ae, ß -> ss); all other Latin
    diacritics fold to their base letter (é -> e, ł -> l, š -> s).

    Must reproduce scripts/fetch_osm_stolpersteine.py's output for every name
    already committed under data/stolpersteine-records/ — those slugs are
    filenames on disk. See tests/test_slug.py, which asserts equivalence across
    every committed street and person name, not a hand-picked sample.
    """
    # Normalise first: scraped input may arrive decomposed (e + U+0301) rather
    # than precomposed (é), and a bare combining mark would survive the fold.
    s = unicodedata.normalize("NFC", (text or "")).lower()
    s = s.translate(_TRANSLATION)
    # Strip remaining diacritics: NFKD splits é into e + combining acute, and
    # the Mn category filter drops the mark. Handles ë, ł, š, ž, ć, ø and the
    # rest of the Latin range without an ever-growing lookup table.
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("ł", "l").replace("ø", "o").replace("đ", "d")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
