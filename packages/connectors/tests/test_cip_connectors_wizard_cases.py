"""Mapping-wizard test exports (ADR-0011, CI0005 sequence 01).

The first tests check that every case and its `expected.yaml` agree with each other. The
`xfail(strict=True)` tests are the wizard's known answers: they fail until sequences 02-07 build
the wizard, and pytest then reports them as passing unexpectedly, so the marker is removed in
the sequence that turns them green.
"""

import csv
import io
from pathlib import Path
from typing import Any

import pytest
import yaml
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "data" / "synthetic" / "wizard_cases"
NAMES = sorted(p.name for p in CASES.iterdir() if (p / "expected.yaml").exists())
PERSONAL = "personal (dropped on read, never shown or sent)"


def _expected(name: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((CASES / name / "expected.yaml").read_text())
    return data


def _headers(name: str, file: str, fmt: dict[str, Any]) -> list[str]:
    """Header of a CSV file or a workbook sheet (``book.xlsx#sheet``), below any title lines."""
    skip = fmt["title_lines_above_header"]
    if "#" in file:
        book, sheet = file.split("#")
        ws = load_workbook(CASES / name / book, read_only=True)[sheet]
        rows = list(ws.iter_rows(min_row=skip + 1, max_row=skip + 1, values_only=True))
        return [str(c) for c in rows[0] if c is not None]
    text = (CASES / name / file).read_text(encoding="utf-8-sig")
    delimiter = {"tab": "\t"}.get(fmt["delimiter"], fmt["delimiter"])
    lines = text.splitlines()[skip:]
    return next(csv.reader(io.StringIO(lines[0]), delimiter=delimiter))


def test_there_are_six_cases_from_four_plants() -> None:
    assert NAMES == ["exact_en", "isah_xlsx", "mes_us", "messy", "ridder_hours", "sap_de"]
    assert {_expected(n)["plant"] for n in NAMES} == {"plant_a", "plant_b", "plant_c", "plant_d"}


@pytest.mark.parametrize("name", NAMES)
def test_every_expected_column_is_in_its_file(name: str) -> None:
    exp = _expected(name)
    for file, columns in exp["columns"].items():
        assert set(columns) <= set(_headers(name, file, exp["format"])), (name, file)


@pytest.mark.parametrize("name", NAMES)
def test_every_case_has_a_known_answer_and_its_needed_files(name: str) -> None:
    exp = _expected(name)
    assert (ROOT / exp["plant_answer"]).exists()
    roles = {
        r
        for f in exp["files"].values()
        for r in ([f["role"]] if isinstance(f["role"], str) else f["role"])
    }
    assert roles & {"events", "hour_bookings"}, "an event log or hour bookings"
    assert {"resources", "calendar"} <= roles, "a steps list and a shift sheet"
    assert exp["flow"]["routes"][0]["share_pct"] > 20, "a main route the canvas can show"


@pytest.mark.parametrize("name", [n for n in NAMES if n != "ridder_hours"])
def test_the_personal_column_is_in_the_file_and_marked(name: str) -> None:
    exp = _expected(name)
    personal = [c for cols in exp["columns"].values() for c, m in cols.items() if m == PERSONAL]
    assert len(personal) == 1, "each event log carries one personal column, to be dropped"


def test_hour_bookings_have_a_lower_confidence_answer() -> None:
    exp = _expected("ridder_hours")
    assert exp["files"]["Urenregistratie.csv"]["role"] == "hour_bookings"
    assert exp["answer"]["constraint"] == "PNT-01"
    assert "lower than high" in exp["answer"]["confidence"]


# --- the wizard's known answers: green once the wizard exists ---------------------------------


@pytest.mark.xfail(strict=True, reason="CI0005 sequence 02 builds the file recogniser")
@pytest.mark.parametrize("name", NAMES)
def test_wizard_sorts_the_files(name: str) -> None:
    from cip_connectors.wizard import recognise_export  # type: ignore[import-not-found]

    found = recognise_export(sorted((CASES / name).iterdir()))
    assert found.summary()["files"] == _expected(name)["files"]


@pytest.mark.xfail(
    strict=True, reason="CI0005 sequences 03-05 build column, code and format matching"
)
@pytest.mark.parametrize("name", NAMES)
def test_wizard_matches_columns_codes_and_formats(name: str) -> None:
    from cip_connectors.wizard import recognise_export

    exp = _expected(name)
    summary = recognise_export(sorted((CASES / name).iterdir())).summary()
    assert summary["columns"] == exp["columns"]
    assert summary["code_tables"] == exp["code_tables"]
    assert summary["format"] == exp["format"]
