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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Loënstraße", "loenstrasse"),   # ë was dropped entirely before NFKD folding
        ("Łódź", "lodz"),
        ("Dvořák", "dvorak"),
        ("Œuvre", "oeuvre"),
        ("Ørsted", "orsted"),
    ],
)
def test_slugify_folds_non_german_latin_diacritics(raw, expected):
    """Victim names in this archive are not only German.

    A diacritic that folds to nothing becomes a hyphen and mangles the filename:
    Loënstraße used to slugify to 'lo-nstrasse'.
    """
    assert slugify(raw) == expected


def test_slugify_is_normalisation_insensitive():
    """Scraped input may arrive decomposed (e + U+0301) rather than precomposed."""
    assert slugify("Linn\u00e9stra\u00dfe") == slugify("Linne\u0301stra\u00dfe")
    assert slugify("M\u00fcller") == slugify("Mu\u0308ller")


def test_slugify_matches_osm_script_across_every_committed_name():
    """Equivalence with the OSM script, fuzzed over the real archive.

    These slugs are filenames on disk under data/stolpersteine-records/, so a
    divergence renames records and orphans them. Four hand-picked strings are
    not enough; this walks every street, house number, district and person name
    actually committed.

    The single permitted divergence is 'Loënstraße': the OSM script drops the
    'ë' and produces the mangled 'lo-nstrasse'. Folding it correctly is the
    point of this change, and the one affected record is documented in
    plans/004-findings.md.
    """
    import json
    from pathlib import Path

    osm = load_script("osm_mod_slugcheck", "scripts/fetch_osm_stolpersteine.py")
    records_dir = Path(__file__).resolve().parent.parent / "data" / "stolpersteine-records"
    if not records_dir.is_dir():
        pytest.skip("archive not present")

    names: set[str] = set()
    for path in records_dir.glob("*/*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        address = record.get("address") or {}
        person = record.get("person") or {}
        for value in (
            address.get("street"),
            address.get("house_number"),
            address.get("district"),
            person.get("name"),
        ):
            if value:
                names.add(value)

    assert len(names) > 1000, "expected the full archive, got a stub"
    known_divergent = {"Loënstraße"}
    diverging = {n for n in names if slugify(n) != osm.slugify(n)}
    assert diverging == known_divergent
