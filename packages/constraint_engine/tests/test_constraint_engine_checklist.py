"""Checklist parsed from docs/input-data.md and checked against plants."""

import shutil
from pathlib import Path

import pytest

from constraint_engine.diagnose import main
from constraint_engine.io.plant_loader import load_plant
from constraint_engine.quality.checklist import (
    OPTIONAL_SET,
    checklist,
    minimum_set,
    parse_requirements,
)

ROOT = Path(__file__).resolve().parents[3]
DOC = ROOT / "docs" / "input-data.md"
PLANT_A = ROOT / "data" / "synthetic" / "plant_a"


def test_requirements_come_from_the_document() -> None:
    reqs = parse_requirements(DOC.read_text())
    assert sorted(r.number for r in reqs) == list(range(1, 29))
    by_number = {r.number: r for r in reqs}
    assert by_number[12].level == "Must" and by_number[12].min_weeks == 8
    assert by_number[9].min_weeks == 8
    assert by_number[10].level == "Later"
    assert by_number[13].level == "Should"
    # ADR-0009: products and routings raise confidence; they are not needed to start
    assert {by_number[n].level for n in (4, 5, 6, 9, 17, 19, 28)} == {"Should"}
    assert {by_number[n].level for n in (3, 12, 16)} == {"Must"}


def test_plant_a_meets_every_must_and_should() -> None:
    items = checklist(parse_requirements(DOC.read_text()), load_plant(PLANT_A))
    statuses = {i.requirement.number: i.status for i in items}
    assert all(statuses[n] in ("ok", "n/a", "check") for n in statuses)
    assert statuses[19] == "check"  # holidays: absence cannot be proven from data
    assert statuses[24] == "n/a"  # accounts are not plant data


def test_missing_events_and_scrap_show_as_missing(tmp_path: Path) -> None:
    root = tmp_path / "plant"
    shutil.copytree(PLANT_A, root, ignore=shutil.ignore_patterns("erp_export"))
    (root / "events.csv").unlink()
    statuses = {
        i.requirement.number: i.status
        for i in checklist(parse_requirements(DOC.read_text()), load_plant(root))
    }
    assert statuses[12] == "missing" and statuses[14] == "missing" and statuses[13] == "missing"


def test_cli_quality_section_prints_report_and_checklist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    md = tmp_path / "quality.md"
    assert main([str(PLANT_A), "--section", "quality", "--md", str(md)]) == 0
    out = capsys.readouterr().out
    assert "Data quality score: 94 / 100" in out
    assert "No breakdowns recorded for PCK-01" in out
    assert "Data checklist (docs/input-data.md):" in out
    text = md.read_text()
    assert (
        "# Data quality report" in text
        and "## Data checklist" in text
        and "| 12 | Event log (touchpoints) |" in text
    )


def test_minimum_set_rolls_up_item_statuses() -> None:
    from constraint_engine.quality.checklist import ChecklistItem, Requirement

    def item(n: int, status: str) -> ChecklistItem:
        return ChecklistItem(Requirement(n, "s", "d", "k", "Must", None), status, "")

    items = [
        item(12, "missing"),
        item(3, "ok"),
        item(16, "ok"),
        item(9, "ok"),
        item(4, "ok"),
        item(6, "missing"),
        item(19, "check"),
    ]
    assert {m.key: m.status for m in minimum_set(items)} == {
        "events": "missing",
        "steps": "ok",
        "shifts": "ok",
    }
    optional = {m.key: m.status for m in minimum_set(items, OPTIONAL_SET)}
    assert optional["orders"] == "ok"
    assert optional["routings"] == "partial"
    assert optional["products"] == "missing"
    assert optional["holidays"] == "check"


def test_the_event_log_steps_and_shifts_are_enough_to_start(tmp_path: Path) -> None:
    """Plant D with only its steps list, shift sheet (with team sizes) and event log: the minimum
    is met, the optional files are listed as missing, and the team is still found (ADR-0009)."""
    from constraint_engine.detection import detect_periods
    from constraint_engine.facts import measured_facts
    from constraint_engine.quality.report import quality_report

    root = tmp_path / "plant"
    root.mkdir()
    sheet = ("calendar.csv", "teams.csv", "team_shifts.csv")
    for name in ("plant.json", "stations.csv", "resources.csv", *sheet, "events.csv"):
        shutil.copy(ROOT / "data" / "synthetic" / "plant_d" / name, root / name)
    plant = load_plant(root)
    items = checklist(parse_requirements(DOC.read_text()), plant)
    assert {m.key: m.status for m in minimum_set(items)} == {
        "events": "ok",
        "steps": "ok",
        "shifts": "ok",
    }
    optional = {m.key: m.status for m in minimum_set(items, OPTIONAL_SET)}
    assert optional["orders"] == "missing" and optional["products"] == "missing"
    assert not [g for g in quality_report(plant).gaps if g.code == "missing_file"]
    facts = measured_facts(plant)
    whole = next(d for kind, d in detect_periods(plant, facts, kinds=("all",)) if kind == "all")
    assert whole.resource_code == "FINISH-TEAM"
