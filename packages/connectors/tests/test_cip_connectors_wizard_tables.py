"""Reading a whole export as it comes (ADR-0011 §2, CI0005 sequence 02)."""

import shutil
from pathlib import Path

from cip_connectors.wizard import recognise_export
from cip_connectors.wizard.tables import read_export

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "data" / "synthetic" / "wizard_cases"


def test_title_lines_totals_and_byte_order_mark_are_not_rows() -> None:
    tables = read_export(sorted((CASES / "messy").glob("*.[cx]*")))
    assert {t.id for t in tables} == {
        "planning.xlsx#Rooster",
        "planning.xlsx#Teams",
        "planning.xlsx#Teamrooster",
        "rapport_jobs.csv",
        "rapport_scans.csv",
        "rapport_werkplekken.csv",
    }
    for t in tables:
        assert (t.title_lines, t.totals_lines, t.problem) == (3, 1, None), t.id
        assert t.header[0] in ("Workstation", "Job", "Team"), t.id
    scans = next(t for t in tables if t.id == "rapport_scans.csv")
    assert scans.delimiter == ";" and len(scans.rows) == 28541


def test_personal_values_never_enter_a_row() -> None:
    scans = next(t for t in read_export([CASES / "mes_us" / "labor_transactions.csv"]))
    assert scans.personal_columns == ["Badge"]
    assert "Badge" not in scans.header
    assert not any("TEST-OPERATOR" in str(v) for r in scans.rows for v in r.values())


def test_tab_separated_text_files_are_tables() -> None:
    [t] = read_export([CASES / "sap_de" / "CRHD_Arbeitsplaetze.txt"])
    assert (t.delimiter, t.header) == ("\t", ["Arbeitsplatz", "Kurztext", "Kostenstelle"])


def test_a_file_that_cannot_be_read_says_why_and_the_rest_continues(tmp_path: Path) -> None:
    for f in (CASES / "exact_en").iterdir():
        if f.suffix == ".csv":
            shutil.copy(f, tmp_path / f.name)
    (tmp_path / "empty.csv").write_text("")
    (tmp_path / "broken.xlsx").write_bytes(b"not a workbook")
    (tmp_path / "scan.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "notes.txt").write_text("just one line of notes\n")
    found = recognise_export(sorted(tmp_path.iterdir()))
    problems = {t.id: t.problem for t in found.tables if t.problem}
    assert problems == {
        "empty.csv": "empty",
        "broken.xlsx": "unreadable_excel",
        "scan.pdf": "not_a_table_file",
        "notes.txt": "single_column",
    }
    assert found.minimum() == {
        "events": ["ShopFloorEvents.csv"],
        "steps": ["Resources.csv"],
        "calendar": ["Roster.csv"],
    }
