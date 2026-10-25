"""A plant built from records (database rows) equals the plant read from its files (ADR-0010)."""

import json
from pathlib import Path
from typing import Any

import pytest

from constraint_engine.detection import detect_periods
from constraint_engine.facts import measured_facts
from constraint_engine.io.plant_loader import LoadedPlant, load_plant
from constraint_engine.io.records import load_records

SYNTHETIC = Path(__file__).resolve().parents[3] / "data" / "synthetic"
ATTRS = (
    "stations",
    "resources",
    "products",
    "orders",
    "events",
    "calendar",
    "resource_operations",
    "changeovers",
    "overtime",
    "capacity_costs",
    "outsourcing",
    "teams",
    "team_shifts",
)


def _as_rows(plant: LoadedPlant) -> dict[str, list[dict[str, Any]]]:
    """What the database gives back: plain values, list columns joined by ','."""

    def row(model: Any) -> dict[str, Any]:
        return {
            k: ",".join(v) if isinstance(v, tuple) else v for k, v in model.model_dump().items()
        }

    rows = {a: [row(m) for m in getattr(plant, a)] for a in ATTRS}
    rows["routings"] = [{"sku": r.sku, **row(s)} for r in plant.routings for s in r.steps]
    return rows


@pytest.mark.parametrize("name", ["plant_a", "plant_b", "plant_c", "plant_d"])
def test_records_give_the_same_plant_and_answer_as_files(name: str) -> None:
    files = load_plant(SYNTHETIC / name)
    info = json.loads((SYNTHETIC / name / "plant.json").read_text())
    rows = load_records(info, _as_rows(files))
    assert rows.row_errors == [] and rows.missing_files == {}
    assert rows.plant == files.plant
    for attr in (*ATTRS, "routings"):
        assert getattr(rows, attr) == getattr(files, attr), attr
    want = detect_periods(files, measured_facts(files), kinds=("all",))[0][1]
    got = detect_periods(rows, measured_facts(rows), kinds=("all",))[0][1]
    assert (got.resource_code, got.kind) == (want.resource_code, want.kind)


def test_empty_required_records_are_reported_missing_and_bad_rows_are_listed() -> None:
    info = json.loads((SYNTHETIC / "plant_a" / "plant.json").read_text())
    loaded = load_records(info, {"events": [{"event_id": "x"}]})
    assert set(loaded.missing_files) == {
        "stations.csv",
        "resources.csv",
        "events.csv",
        "calendar.csv",
    }
    assert [(e.file, e.line) for e in loaded.row_errors] == [("events.csv", 1)]
