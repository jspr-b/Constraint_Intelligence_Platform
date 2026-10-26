"""Mapping-wizard test exports (ADR-0011, CI0005 sequence 01).

The first tests check that every case and its `expected.yaml` agree with each other. Then the
wizard's known answers: file roles and links (sequence 02). The `xfail(strict=True)` tests are
the answers still to build; pytest reports them as passing unexpectedly once they work, so the
marker is removed in the sequence that turns them green.
"""

import csv
import io
from pathlib import Path
from typing import Any

import pytest
import yaml
from openpyxl import load_workbook

from cip_connectors.wizard import recognise_export

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


# --- the wizard's known answers ----------------------------------------------------------------


def _files(name: str) -> list[Path]:
    return sorted(p for p in (CASES / name).iterdir() if p.name != "expected.yaml")


@pytest.mark.parametrize("name", NAMES)
def test_wizard_sorts_the_files(name: str) -> None:
    found = recognise_export(_files(name)).summary()["files"]
    expected = {
        f: {"role": None if v["role"] == "not_used" else v["role"]}
        for f, v in _expected(name)["files"].items()
    }
    assert found == expected


@pytest.mark.parametrize("name", NAMES)
def test_wizard_sorts_the_files_by_content_alone(name: str, tmp_path: Path) -> None:
    """Files renamed table0, table1, ...: the roles hold, only less sure."""
    renamed = {}
    for i, f in enumerate(_files(name)):
        target = tmp_path / f"table{i}{f.suffix}"
        target.write_bytes(f.read_bytes())
        renamed[target.name] = f.name
    found = recognise_export(sorted(tmp_path.iterdir()))
    expected = _expected(name)["files"]
    files = found.summary()["files"]
    for r in found.roles:
        file, _, sheet = r.table.partition("#")
        original = renamed[file] + (f"#{sheet}" if sheet else "")
        want = expected[original]["role"]
        if want == "not_used":
            assert r.role is None, original
        else:
            # A sheet keeps its name inside the renamed workbook, so it may still be "sure".
            sure = ("likely", "sure") if sheet else ("likely",)
            assert files[r.table]["role"] == want and r.sure in sure, original


@pytest.mark.parametrize("name", NAMES)
def test_wizard_links_the_event_log_to_the_steps_list(name: str) -> None:
    exp = _expected(name)
    log = next(f for f, v in exp["files"].items() if v["role"] in ("events", "hour_bookings"))
    steps = next(f for f, v in exp["files"].items() if v["role"] == ["resources", "stations"])

    def column(file: str, field: str) -> str:
        return str(
            next(
                c
                for c, m in exp["columns"][file].items()
                if m == field or (isinstance(m, list) and field in m)
            )
        )

    want = (
        log,
        column(log, "events.resource_code"),
        steps,
        column(steps, "resources.resource_code"),
    )
    links = recognise_export(_files(name)).links
    assert want in {(k.table, k.column, k.to_table, k.to_column) for k in links}


@pytest.mark.xfail(
    strict=True, reason="CI0005 sequences 03-05 build column, code and format matching"
)
@pytest.mark.parametrize("name", NAMES)
def test_wizard_matches_columns_codes_and_formats(name: str) -> None:
    exp = _expected(name)
    summary = recognise_export(_files(name)).summary()
    assert summary["columns"] == exp["columns"]
    assert summary["code_tables"] == exp["code_tables"]
    assert summary["format"] == exp["format"]
