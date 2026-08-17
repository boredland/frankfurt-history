"""Tests for the records backfill in scripts/build_stolpersteine.py.

The frankfurt.de crawl is the primary source for article text, but it does not
cover every stone. These tests pin the address matching that decides whether a
record needs an article of its own, since a false negative silently duplicates
a stone on the map and a false positive silently hides a biography.
"""

import json
from pathlib import Path

import pytest

from tests.conftest import load_script

build_mod = load_script("build_stolpersteine_mod", "scripts/build_stolpersteine.py")
normalize_address = build_mod.normalize_address
tidy_address = build_mod.tidy_address
record_person_names = build_mod.record_person_names

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    ("records_form", "frankfurt_de_form"),
    [
        ("Bolongarostr. 128", "Bolongarostraße 128"),
        ("Radilostr. 29", "Radilostraße 29"),
        ("Marktstr. 45", "Marktstraße 45"),
        ("Textorstr. 79", "Textorstraße 79"),
        ("Rödelheimer Landstr. 24", "Rödelheimer Landstraße 24"),
        ("Alt Heddernheim 33", "Alt-Heddernheim 33"),
        ("Alt Fechenheim 105", "Alt-Fechenheim 105"),
        ("Alt Rödelheim 38", "Alt-Rödelheim 38"),
        ("Bergerstraße 200", "Berger Straße 200"),
        ("Kronbergerstraße 30", "Kronberger Straße 30"),
        ("Adolf-Häuser-Straße 14", "Adolf-Haeuser-Straße 14"),
    ],
)
def test_address_variants_of_one_stone_compare_equal(records_form, frankfurt_de_form):
    """Records come from OSM, articles from frankfurt.de; both spell it their way."""
    assert normalize_address(records_form) == normalize_address(frankfurt_de_form)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Marktstr. 45", "Marktstr. 51"),
        ("Bolongarostr. 128", "Bolongarostr. 132"),
        ("Alt Rödelheim 12", "Alt Rödelheim 20"),
        ("Tevestraße 27", "Tevestraße 43"),
        ("Kronbergerstraße 5", "Kronbergerstraße 30"),
    ],
)
def test_distinct_stones_stay_distinct(left, right):
    """House number carries the identity: over-normalising would merge stones."""
    assert normalize_address(left) != normalize_address(right)


def test_normalize_address_tolerates_missing_input():
    assert normalize_address(None) == ""
    assert normalize_address("") == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Radilostr. 29", "Radilostraße 29"),
        ("Rödelheimer Landstr. 24", "Rödelheimer Landstraße 24"),
        ("Hostatostaße. 3", "Hostatostaße 3"),
        ("Fuchshohl 27", "Fuchshohl 27"),
        ("Alt Rödelheim 12", "Alt Rödelheim 12"),
    ],
)
def test_tidy_address_expands_abbreviation_for_display(raw, expected):
    assert tidy_address(raw) == expected


def test_person_names_group_by_surname():
    records = [
        {"person": {"name": "Leopold Zuntz"}},
        {"person": {"name": "Cäcilie Zuntz"}},
        {"person": {"name": "Hermann Zuntz"}},
    ]
    assert record_person_names(records) == "Zuntz, Leopold, Cäcilie und Hermann"


def test_person_names_falls_back_to_commemorates_for_location_records():
    """Location-level records have no person.name but do list their victims."""
    records = [
        {"person": {"name": None}, "commemorates": ["Schatzmann, Lilly", "Kahn, Paula"]}
    ]
    assert record_person_names(records) == "Schatzmann, Lilly; Kahn, Paula"


def test_person_names_is_empty_when_nothing_is_known():
    assert record_person_names([{"person": {"name": None}}]) == ""


def test_every_biography_bearing_record_reaches_an_article():
    """The regression this backfill exists to prevent.

    A record carrying biography text whose address has no article is a
    biography that ships to nobody. Records without biography text are out of
    scope: there is nothing to render.
    """
    records_dir = REPO_ROOT / "data" / "stolpersteine-records" / "frankfurt-am-main"
    theme_dir = REPO_ROOT / "data" / "stolpersteine"
    if not records_dir.is_dir() or not theme_dir.is_dir():
        pytest.skip("archive not present")

    built = build_mod.built_addresses()
    assert len(built) > 700, "expected the full archive, got a stub"

    orphaned = []
    for path in records_dir.glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if not any(b.get("text") for b in (record.get("biographies") or [])):
            continue
        if not record.get("coords"):
            continue
        if normalize_address((record.get("address") or {}).get("formatted")) not in built:
            orphaned.append(path.name)

    assert orphaned == []
