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
