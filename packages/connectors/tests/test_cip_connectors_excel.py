from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from cip_connectors.convert import convert
from cip_connectors.excel import read_xlsx
from cip_connectors.importer import import_export
from cip_connectors.mapping import FieldRule, MappingSet

PLANT_A = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "plant_a"


def keep_all(_: str) -> bool:
    return False


def test_csv_and_xlsx_give_identical_standard_layout(
    tmp_path: Path, events_mapping: dict[str, Any]
) -> None:
    mapping = MappingSet.model_validate(events_mapping)
    clean = PLANT_A / "erp_export" / "clean"
    import_export(clean / "csv", mapping, tmp_path / "from_csv")
    import_export(clean / "xlsx", mapping, tmp_path / "from_xlsx")
    a = (tmp_path / "from_csv" / "events.csv").read_text()
    b = (tmp_path / "from_xlsx" / "events.csv").read_text()
    assert a == b
    assert len(a.splitlines()) > 1000


def test_header_detection_merged_cells_and_trailing_rows(tmp_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Export from ERP", None, None])  # title row above the header
    ws.append([None, None, None])
    ws.append(["Werkplek", "Bon", "Medewerker"])
    ws.append(["LAS1", "24001", "TEST-MEDEWERKER-01"])
    ws.append([None, "24002", "TEST-MEDEWERKER-02"])
    ws.merge_cells("A4:A5")  # one machine for two rows
    ws.append([None, None, None])
    ws.append([None, None, None])
    path = tmp_path / "t.xlsx"
    wb.save(path)
    table = read_xlsx(path, lambda c: c == "Medewerker")
    assert table.header == ["Werkplek", "Bon"]
    assert table.dropped_columns == ["Medewerker"]
    assert [r for _, r in table.rows] == [
        {"Werkplek": "LAS1", "Bon": "24001"},
        {"Werkplek": "LAS1", "Bon": "24002"},
    ]
    assert [line for line, _ in table.rows] == [4, 5]


def test_excel_serial_date() -> None:
    mapping = MappingSet.model_validate(
        {"source_system": "X", "timezone": "Europe/Amsterdam", "tables": []}
    )
    rule = FieldRule.model_validate({"from": "t", "type": "datetime"})
    # 46308.385416... = 2026-10-13 09:15 local
    serial = (datetime(2026, 10, 13, 9, 15) - datetime(1899, 12, 30)).total_seconds() / 86400
    assert convert(serial, rule, mapping, "t") == "2026-10-13T07:15:00Z"
