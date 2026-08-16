"""Characterization tests for scripts/merge.py.

These pin CURRENT behaviour, including known defects.

A test whose name ends in KNOWN_DEFECT asserts behaviour that is WRONG and will
be deliberately changed by a follow-up commit. They use positive assertions
rather than `@pytest.mark.xfail` on purpose: xfail would let the behaviour
change in *either* direction without anyone noticing, whereas a positive
assertion fails loudly the moment the defect is fixed — which is exactly the
signal the follow-up needs. When that commit lands, invert the assertion and
drop the KNOWN_DEFECT suffix; do not delete the test.
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


def test_clean_body_keeps_non_latin1_names(merge_mod):
    """Victim and place names are not only German: Ł, Š, Ć, Ž must survive."""
    body = "Ein ausreichend langer Absatz als Kontext hier.\n\nŁódź\n"
    assert "Łódź" in merge_mod.clean_body(body)


def test_clean_body_drops_whitespace_only_block(merge_mod):
    body = "Ein ausreichend langer Absatz als Kontext hier.\n\n   \n"
    out = merge_mod.clean_body(body)
    assert "Absatz" in out
    assert out.strip().endswith("hier.")


def test_clean_body_still_drops_markup_only_blocks(merge_mod):
    """The negative case: the narrowed rule must still remove real junk.

    Without this, a regression that simply deleted the rule would pass every
    other test in this file.
    """
    body = (
        "Ein ausreichend langer Absatz als Kontext hier.\n\n"
        "<br/>\n\n"
        "Ein zweiter ausreichend langer Absatz als Kontext.\n"
    )
    out = merge_mod.clean_body(body)
    assert "<br/>" not in out
    assert "Absatz als Kontext hier" in out


def test_clean_body_drops_entity_only_block(merge_mod):
    """&nbsp; has an alphanumeric entity NAME; it must still count as empty.

    Asserted in trailing position. An entity block sandwiched between two
    paragraphs is absorbed earlier by the paragraph-joining heuristic
    (scripts/merge.py:204-219) and never reaches the readable-text rule — a
    pre-existing behaviour of that heuristic, out of scope for this change.
    """
    body = "Ein ausreichend langer Absatz als Kontext hier.\n\n&nbsp;\n"
    out = merge_mod.clean_body(body)
    assert "&nbsp;" not in out
    assert "Absatz als Kontext hier" in out


def test_has_readable_text_unit(merge_mod):
    """Direct unit coverage of the predicate, independent of the surrounding
    heuristics that may consume a block before it is reached."""
    assert merge_mod._has_readable_text("Städtische Bühnen")
    assert merge_mod._has_readable_text("Łódź")
    assert merge_mod._has_readable_text('<span class="tab2">K</span>')
    assert not merge_mod._has_readable_text("   ")
    assert not merge_mod._has_readable_text("<br/>")
    assert not merge_mod._has_readable_text("&nbsp;")
    assert not merge_mod._has_readable_text("<p>&nbsp;</p>")


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


def test_de_structural_override_applies_to_en_but_skips_clean_body_KNOWN_DEFECT(
    merge_mod, tmp_path, monkeypatch
):
    """PLAN.md: DE structural fields (coordinates/categories/filters/id) apply to
    EN when no EN-specific override exists.

    KNOWN DEFECT pinned here: that code path at scripts/merge.py:314 writes
    `base_body` directly via serialize_frontmatter(), bypassing clean_body(),
    while every other path cleans the body. An EN article reached through a DE
    structural override therefore keeps its duplicated H1 title and subtitle
    that every other article has stripped.
    """
    data = tmp_path / "data"
    overrides = tmp_path / "overrides"
    content = tmp_path / "content"
    for lang in ("de", "en"):
        (data / lang / "theme").mkdir(parents=True)
    (overrides / "de" / "theme").mkdir(parents=True)

    body = "# Titel\n\n*Untertitel*\n\nEin ausreichend langer Absatz als Inhalt.\n"
    for lang in ("de", "en"):
        (data / lang / "theme" / "0001-x.md").write_text(
            f'---\nid: 1\ntitle: "Titel"\ncoordinates: [1.0, 2.0]\n---\n\n{body}',
            encoding="utf-8",
        )
    (overrides / "de" / "theme" / "0001-x.md").write_text(
        "---\ncoordinates: [50.1105, 8.6821]\n---\n", encoding="utf-8"
    )

    monkeypatch.setattr(merge_mod, "DATA_DIR", data)
    monkeypatch.setattr(merge_mod, "OVERRIDES_DIR", overrides)
    monkeypatch.setattr(merge_mod, "CONTENT_DIR", content)
    merge_mod.merge_lang("de")
    merge_mod.merge_lang("en")

    de_out = (content / "de" / "theme" / "0001-x.md").read_text(encoding="utf-8")
    en_out = (content / "en" / "theme" / "0001-x.md").read_text(encoding="utf-8")

    # The structural override reached both locales.
    assert "50.1105" in de_out
    assert "50.1105" in en_out

    # DE went through clean_body; EN did not.
    assert "# Titel" not in de_out
    assert "# Titel" in en_out

