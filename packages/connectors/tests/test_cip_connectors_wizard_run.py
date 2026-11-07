"""An import runs from the confirmed summary (ADR-0011, CI0005 seq 05): each test export, mapped
by what the wizard found and nothing else, gives its plant's known answer.

The client is taken to say yes to every suggestion. Steps keep the plant's own codes, so the
answer is compared through the case's code table (``LAK1`` is plant A's ``PNT-01``).
"""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from cip_connectors.importer import import_export
from cip_connectors.mapping import MappingSet
from cip_connectors.wizard import recognise_export
from cip_connectors.wizard.plan import Plan, PlanColumn, build_mapping, plan_from, value_type
from constraint_engine.detection import detect_periods
from constraint_engine.facts import measured_facts
from constraint_engine.io.plant_loader import load_plant

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "data" / "synthetic" / "wizard_cases"
SCANS = ["exact_en", "isah_xlsx", "mes_us", "messy", "sap_de"]


def _expected(name: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((CASES / name / "expected.yaml").read_text())
    return data


def _mapping(name: str) -> MappingSet:
    found = recognise_export(sorted((CASES / name).iterdir()))
    return build_mapping(plan_from(found))


def _run(name: str, out: Path) -> Any:
    report = import_export(
        CASES / name,
        _mapping(name),
        out,
        plant={"plant_code": "PLANT-W", "name": "Wizard", "timezone_iana": "Europe/Amsterdam"},
    )
    return report


@pytest.mark.parametrize("name", SCANS)
def test_an_export_mapped_from_its_summary_gives_the_plant_answer(
    name: str, tmp_path: Path
) -> None:
    exp = _expected(name)
    report = _run(name, tmp_path)
    assert not report.missing_required, report.missing_required
    assert report.rows_written["events"] > 1000
    answer = yaml.safe_load((ROOT / exp["plant_answer"]).read_text())
    plant = load_plant(tmp_path)
    ((_, found),) = detect_periods(plant, measured_facts(plant), (), kinds=("all",))
    own = {v: k for k, v in exp["code_tables"].get("resource", {}).items()}
    want = answer["constraint"]
    assert (found.resource_code or "none") == own.get(want, want), (name, found.reasons)
    assert found.kind == answer["constraint_kind"]


def test_the_steps_keep_the_plant_codes_and_the_client_names(tmp_path: Path) -> None:
    found = recognise_export(sorted((CASES / "exact_en").iterdir()))
    plan = plan_from(found)
    code = found.steps[0].code
    plan.steps = {code: {"name": "Laser 1", "kind": "manual"}}
    import_export(CASES / "exact_en", build_mapping(plan), tmp_path)
    rows = (tmp_path / "resources.csv").read_text().splitlines()
    mine = next(r for r in rows if r.startswith(f"{code},"))
    assert mine.split(",")[1:4:2] == ["Laser 1", "manual"]


def test_codes_the_client_left_out_are_left_out_not_rejected(tmp_path: Path) -> None:
    found = recognise_export(sorted((CASES / "exact_en").iterdir()))
    plan = plan_from(found)
    plan.meanings["events.event_type"]["REJECTED"] = "skip"
    report = import_export(CASES / "exact_en", build_mapping(plan), tmp_path)
    assert sum(len(v) for v in report.excluded.values()) > 0
    assert not [e for e in report.row_errors if e.code == "unknown_code"]


def test_a_date_and_time_in_two_columns_and_hours_become_one_moment_and_minutes(
    tmp_path: Path,
) -> None:
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "log.csv").write_text(
        "Job;Step;What;Day;Clock;Hours\nJ1;S1;START;20.07.2026;06:30:00;1,5\n"
    )
    plan = Plan(
        tables={"log.csv": "events"},
        columns=[
            PlanColumn("log.csv", "Job", ["events.order_id"]),
            PlanColumn("log.csv", "Step", ["events.resource_code"]),
            PlanColumn("log.csv", "What", ["events.event_type"]),
            PlanColumn("log.csv", "Day", ["events.at"], "date"),
            PlanColumn("log.csv", "Clock", ["events.at"], "time"),
        ],
        meanings={"events.event_type": {"START": "start"}},
        time_formats={("log.csv", "Day"): "%d.%m.%Y", ("log.csv", "Clock"): "%H:%M:%S"},
        decimal=",",
    )
    report = import_export(tmp_path / "in", build_mapping(plan), tmp_path / "out")
    assert not report.row_errors, report.row_errors
    line = (tmp_path / "out" / "events.csv").read_text().splitlines()[1]
    assert "2026-07-20T04:30:00Z" in line  # 06:30 Amsterdam summer time
    assert value_type("routings.standard_setup_min") == "decimal"
    assert value_type("calendar.covered") == "bool"
    assert value_type("orders.order_value_eur_cents") == "eur_cents"


def test_the_mapping_can_be_stored_and_read_back() -> None:
    mapping = _mapping("sap_de")
    again = MappingSet.model_validate(json.loads(mapping.model_dump_json(by_alias=True)))
    assert again == mapping
