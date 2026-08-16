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
