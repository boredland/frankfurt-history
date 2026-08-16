"""Characterization tests for scripts/geojson.py frontmatter and coordinate handling."""


def _write_poi(tmp_path, name, frontmatter):
    path = tmp_path / name
    path.write_text(f"---\n{frontmatter}\n---\n\nBody.\n", encoding="utf-8")
    return path


def test_parse_frontmatter_parses_coordinate_list_as_floats(geojson_mod, tmp_path):
    poi = _write_poi(tmp_path, "0001-x.md", "id: 1\ncoordinates: [50.1105, 8.6821]")
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
