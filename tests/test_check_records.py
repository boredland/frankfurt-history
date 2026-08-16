"""Tests for the record consistency checker."""

import json

from tests.conftest import load_script

check = load_script("check_records_mod", "scripts/check_records.py")


def _record(name, street, house, bios=0):
    return {
        "id": f"frankfurt-am-main/{street}-{house}",
        "person": {"name": name},
        "address": {"street": street, "house_number": house},
        "coords": [50.1, 8.6],
        "biographies": [{"text": "x"} for _ in range(bios)],
        "images": [],
        "enrichers": {},
    }


def test_addr_key_folds_accents_consistently():
    a = check.addr_key(_record("X", "Linnéstraße", "27"))
    b = check.addr_key(_record("Y", "Linnestrasse", "27"))
    assert a == b


def test_addr_key_handles_missing_address():
    assert check.addr_key({"address": {}}) == ("", "")
    assert check.addr_key({}) == ("", "")


def test_load_records_reads_city_dir(tmp_path, monkeypatch):
    city = tmp_path / "testcity"
    city.mkdir()
    (city / "a.json").write_text(
        json.dumps(_record("Anna Muster", "Teststraße", "1")), encoding="utf-8"
    )
    monkeypatch.setattr(check, "RECORDS_DIR", tmp_path)
    records, corrupt = check.load_records("testcity")
    assert len(records) == 1
    assert corrupt == 0
    assert records[0][1]["person"]["name"] == "Anna Muster"


def test_load_records_survives_corrupt_json(tmp_path, monkeypatch, capsys):
    city = tmp_path / "testcity"
    city.mkdir()
    (city / "bad.json").write_text("{not json", encoding="utf-8")
    (city / "good.json").write_text(
        json.dumps(_record("Anna Muster", "Teststraße", "1")), encoding="utf-8"
    )
    monkeypatch.setattr(check, "RECORDS_DIR", tmp_path)
    records, corrupt = check.load_records("testcity")
    assert len(records) == 1
    assert corrupt == 1
    # Diagnostics must go to stderr so --json stays parseable on stdout.
    captured = capsys.readouterr()
    assert "CORRUPT" in captured.err
    assert "CORRUPT" not in captured.out


def test_main_exits_nonzero_when_location_is_split(tmp_path, monkeypatch, capsys):
    """A location holding both an anonymous and a named record is the core defect."""
    city = tmp_path / "testcity"
    city.mkdir()
    (city / "anon.json").write_text(
        json.dumps(_record(None, "Teststraße", "1", bios=1)), encoding="utf-8"
    )
    (city / "named.json").write_text(
        json.dumps(_record("Anna Muster", "Teststraße", "1")), encoding="utf-8"
    )
    monkeypatch.setattr(check, "RECORDS_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["check_records.py", "--city", "testcity"])
    assert check.main() == 1
    out = capsys.readouterr().out
    assert "addresses split anon+named:         1" in out
    assert "biographies stranded on anonymous:  1" in out


def test_main_exits_zero_when_clean(tmp_path, monkeypatch):
    city = tmp_path / "testcity"
    city.mkdir()
    (city / "named.json").write_text(
        json.dumps(_record("Anna Muster", "Teststraße", "1")), encoding="utf-8"
    )
    monkeypatch.setattr(check, "RECORDS_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["check_records.py", "--city", "testcity"])
    assert check.main() == 0


def test_main_exits_nonzero_on_corrupt_file(tmp_path, monkeypatch):
    """A corrupt record must fail the gate, not be silently skipped."""
    city = tmp_path / "testcity"
    city.mkdir()
    (city / "bad.json").write_text("{not json", encoding="utf-8")
    (city / "good.json").write_text(
        json.dumps(_record("Anna Muster", "Teststraße", "1")), encoding="utf-8"
    )
    monkeypatch.setattr(check, "RECORDS_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["check_records.py", "--city", "testcity"])
    assert check.main() == 1


def test_main_exits_nonzero_when_records_dir_missing(tmp_path, monkeypatch):
    """An empty or wrong path must fail loudly, not report a clean archive."""
    monkeypatch.setattr(check, "RECORDS_DIR", tmp_path / "nope")
    monkeypatch.setattr("sys.argv", ["check_records.py"])
    assert check.main() == 1


def test_main_exits_nonzero_when_no_records_found(tmp_path, monkeypatch):
    city = tmp_path / "emptycity"
    city.mkdir()
    monkeypatch.setattr(check, "RECORDS_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["check_records.py", "--city", "emptycity"])
    assert check.main() == 1


def test_json_output_is_parseable_despite_corrupt_file(tmp_path, monkeypatch, capsys):
    """--json must emit valid JSON on stdout even when diagnostics are printed."""
    city = tmp_path / "testcity"
    city.mkdir()
    (city / "bad.json").write_text("{not json", encoding="utf-8")
    (city / "anon.json").write_text(
        json.dumps(_record(None, "Teststraße", "1", bios=1)), encoding="utf-8"
    )
    (city / "named.json").write_text(
        json.dumps(_record("Anna Muster", "Teststraße", "1")), encoding="utf-8"
    )
    monkeypatch.setattr(check, "RECORDS_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["check_records.py", "--city", "testcity", "--json"])
    check.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["corrupt_files"] == 1
    assert payload["split_locations"] == 1

