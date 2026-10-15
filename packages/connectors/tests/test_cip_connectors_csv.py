import csv
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from cip_connectors.convert import ConversionError, convert
from cip_connectors.importer import import_export
from cip_connectors.mapping import FieldRule, MappingSet

ROOT = Path(__file__).resolve().parents[3]
PLANT_A = ROOT / "data" / "synthetic" / "plant_a"
EXPORT = PLANT_A / "erp_export" / "clean" / "csv"

KEYS = (
    "event_type",
    "resource_code",
    "station_code",
    "order_id",
    "operation_seq",
    "down_reason_code",
)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def minute(ts: str) -> str:
    return ts[:16]


def test_events_round_trip_to_plant_a(tmp_path: Path, events_mapping: dict[str, Any]) -> None:
    mapping = MappingSet.model_validate(events_mapping)
    report = import_export(EXPORT, mapping, tmp_path)
    assert report.row_errors == []
    assert report.dropped_columns == {"mes_events": ["Medewerker"]}
    imported = Counter(
        (minute(r["at"]), *(r[k] for k in KEYS)) for r in rows(tmp_path / "events.csv")
    )
    original = Counter(
        (minute(r["at"]), *(r[k] for k in KEYS)) for r in rows(PLANT_A / "events.csv")
    )
    assert imported == original


def test_unknown_code_is_a_row_error_not_a_guess(
    tmp_path: Path, events_mapping: dict[str, Any]
) -> None:
    mapping = MappingSet.model_validate(events_mapping)
    defects = PLANT_A / "erp_export" / "defects" / "csv"
    report = import_export(defects, mapping, tmp_path)
    unknown = [e for e in report.row_errors if "LAS9" in e.reason]
    assert len(unknown) == 25
    assert all(e.file == "mes_events.csv" and e.line > 1 for e in unknown)


def test_unmapped_required_field_is_reported_missing(
    tmp_path: Path, events_mapping: dict[str, Any]
) -> None:
    raw = events_mapping
    table = dict(raw["tables"][0])
    table["fields"] = {k: v for k, v in table["fields"].items() if k != "at"}
    mapping = MappingSet.model_validate({**raw, "tables": [table]})
    report = import_export(EXPORT, mapping, tmp_path)
    assert report.missing_required == ["events.at"]
    assert not (tmp_path / "events.csv").exists()


def test_missing_source_table_is_reported(tmp_path: Path, events_mapping: dict[str, Any]) -> None:
    mapping = MappingSet.model_validate(events_mapping)
    report = import_export(tmp_path, mapping, tmp_path / "out")
    assert report.missing_sources == ["mes_events"]


NL = MappingSet.model_validate(
    {
        "source_system": "X",
        "timezone": "Europe/Amsterdam",
        "decimal": ",",
        "datetime_format": "%d-%m-%Y %H:%M",
        "tables": [],
    }
)


@pytest.mark.parametrize(
    ("value", "rule", "expected"),
    [
        ("980,00", {"from": "c", "type": "eur_cents"}, "98000"),
        ("1.234,5", {"from": "c", "type": "decimal"}, "1234.5"),
        ("12", {"from": "c", "type": "int"}, "12"),
        ("ja", {"from": "c", "type": "bool"}, "true"),
        ("nee", {"from": "c", "type": "bool"}, "false"),
        ("13-10-2026 09:15", {"from": "c", "type": "datetime"}, "2026-10-13T07:15:00Z"),
        ("27-01-2026 09:15", {"from": "c", "type": "datetime"}, "2026-01-27T08:15:00Z"),
        (datetime(2026, 10, 13, 9, 15), {"from": "c", "type": "datetime"}, "2026-10-13T07:15:00Z"),
        (
            "LAS1;LAS2",
            {"from": "c", "type": "list", "values": {"LAS1": "WLD-01", "LAS2": "WLD-02"}},
            "WLD-01;WLD-02",
        ),
        ("", {"from": "c", "optional": True}, None),
    ],
)
def test_conversions(value: str | datetime, rule: dict[str, object], expected: str | None) -> None:
    assert convert(value, FieldRule.model_validate(rule), NL, "c") == expected


@pytest.mark.parametrize(
    ("value", "rule", "message"),
    [
        ("12,345", {"from": "c", "type": "eur_cents"}, "two decimals"),
        ("1,5", {"from": "c", "type": "int"}, "whole number"),
        ("misschien", {"from": "c", "type": "bool"}, "yes/no"),
        ("2026-10-13", {"from": "c", "type": "datetime"}, "format"),
        ("", {"from": "c"}, "empty"),
    ],
)
def test_conversion_errors(value: str, rule: dict[str, object], message: str) -> None:
    with pytest.raises(ConversionError, match=message):
        convert(value, FieldRule.model_validate(rule), NL, "c")
