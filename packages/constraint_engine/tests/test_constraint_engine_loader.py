from collections.abc import Callable
from pathlib import Path

import pytest

from constraint_engine.figure import Missing
from constraint_engine.io.plant_loader import load_plant

PlantWriter = Callable[..., Path]


def test_loads_a_complete_tiny_plant(make_plant: PlantWriter) -> None:
    plant = load_plant(make_plant())
    assert not isinstance(plant.plant, Missing)
    assert plant.plant.plant_code == "PLANT-T"
    assert [r.resource_code for r in plant.resources] == ["WLD-01", "PNT-01"]
    assert len(plant.routings) == 1
    assert [s.operation_seq for s in plant.routings[0].steps] == [10, 20]
    assert len(plant.events) == 2
    assert plant.calendar[1].covered is True
    assert plant.row_errors == []
    assert plant.missing_files == {}


def test_missing_file_is_missing_not_an_error(make_plant: PlantWriter) -> None:
    plant = load_plant(make_plant(skip=("events.csv",)))
    assert "events.csv" in plant.missing_files
    assert plant.missing_files["events.csv"].reason == "file not found"
    assert plant.events == []


def test_missing_plant_json(make_plant: PlantWriter) -> None:
    root = make_plant()
    (root / "plant.json").unlink()
    plant = load_plant(root)
    assert isinstance(plant.plant, Missing)
    assert "plant.json" in plant.missing_files


def test_bad_rows_are_reported_with_line_and_reason(
    make_plant: PlantWriter, plant_files: dict[str, str]
) -> None:
    bad_events = plant_files["events.csv"] + (
        "e3,start,2026-10-13 10:00:00,WLD-01,,SO-1,10,16,0,,\n"  # naive time
        "e4,teleport,2026-10-13T10:00:00Z,WLD-01,,SO-1,10,16,0,,\n"  # unknown event type
    )
    plant = load_plant(make_plant(extra={"events.csv": bad_events}))
    assert len(plant.events) == 2
    lines = {(e.file, e.line) for e in plant.row_errors}
    assert lines == {("events.csv", 4), ("events.csv", 5)}
    reasons = " ".join(e.reason for e in plant.row_errors)
    assert "timezone" in reasons and "event_type" in reasons


def test_frames_are_polars(make_plant: PlantWriter) -> None:
    plant = load_plant(make_plant())
    events = plant.frame("events")
    assert events.height == 2
    assert "resource_code" in events.columns
    assert plant.frame("routings").height == 2


@pytest.mark.parametrize("column", ["operator", "employee_name"])
def test_unknown_person_column_is_rejected_as_row_error(
    make_plant: PlantWriter, column: str
) -> None:
    resources = "resource_code,name,station_code," + column + "\nPNT-01,Paint line,PAINT,someone\n"
    plant = load_plant(make_plant(extra={"resources.csv": resources}))
    assert plant.resources == []
    assert any("Extra inputs" in e.reason for e in plant.row_errors)
