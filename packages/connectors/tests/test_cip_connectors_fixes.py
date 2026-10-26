"""Rows fixed or left out in the app (ADR-0010): applied to the rows as read, never to the file.

Known answer from CI0004 sequence 01: the five broken times of `broken/upload_1`, typed in again,
give exactly the events of the clean export.
"""

from pathlib import Path

import yaml

from cip_connectors.importer import import_export
from cip_connectors.mapping import load_mapping
from constraint_engine.io.plant_loader import load_plant

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "data" / "synthetic" / "import_cases"
CLEAN = ROOT / "data" / "synthetic" / "plant_a" / "erp_export" / "clean" / "csv"
MAPPING = load_mapping(ROOT / "packages" / "connectors" / "mappings" / "generic" / "mapping.yaml")
CASE = yaml.safe_load((CASES / "expected_answers.yaml").read_text())["cases"][
    "broken_rows_fixed_in_app"
]
EVENTS = "mes_events.csv"


def test_a_rejected_row_says_its_rule_column_and_value(tmp_path: Path) -> None:
    report = import_export(CASES / "broken" / "upload_1", MAPPING, tmp_path)
    assert [e.line for e in report.row_errors] == [f["line"] for f in CASE["fixes"]]
    first = report.row_errors[0]
    assert (first.file, first.code, first.column, first.value) == (
        EVENTS,
        "not_a_datetime",
        "Tijdstip",
        "not a time",
    )


def test_fixed_rows_give_the_events_of_the_clean_file(tmp_path: Path) -> None:
    source = CASES / "broken" / "upload_1"
    before = (source / EVENTS).read_bytes()
    fixes = {EVENTS: {f["line"]: {f["column"]: f["value"]} for f in CASE["fixes"]}}
    report = import_export(source, MAPPING, tmp_path / "fixed", fixes=fixes)
    assert report.row_errors == [] and report.fixed == {EVENTS: [f["line"] for f in CASE["fixes"]]}
    assert report.fixed_at[EVENTS][101] == "2026-07-20T08:11:00Z"  # 10:11 Amsterdam summer time
    import_export(CLEAN, MAPPING, tmp_path / "clean")
    fixed, clean = load_plant(tmp_path / "fixed"), load_plant(tmp_path / "clean")
    assert len(fixed.events) == CASE["events_after_fixes"]
    assert {e.event_id for e in fixed.events} == {e.event_id for e in clean.events}
    assert (source / EVENTS).read_bytes() == before  # the uploaded file is never changed


def test_a_line_left_out_is_not_imported_and_not_rejected(tmp_path: Path) -> None:
    fixes = {EVENTS: {f["line"]: None for f in CASE["fixes"]}}
    report = import_export(CASES / "broken" / "upload_1", MAPPING, tmp_path, fixes=fixes)
    assert report.row_errors == [] and len(report.excluded[EVENTS]) == 5
    assert report.rows_written["events"] == CASE["events_after_fixes"] - 5


def test_a_fix_that_still_breaks_the_rule_is_rejected_again(tmp_path: Path) -> None:
    line = CASE["fixes"][0]["line"]
    fixes = {EVENTS: {line: {"Tijdstip": "32-07-2026 10:11"}}}
    report = import_export(CASES / "broken" / "upload_1", MAPPING, tmp_path, fixes=fixes)
    again = [e for e in report.row_errors if e.line == line]
    assert len(again) == 1 and again[0].code == "not_a_datetime"
    assert again[0].value == "32-07-2026 10:11"
