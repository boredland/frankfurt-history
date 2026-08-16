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
