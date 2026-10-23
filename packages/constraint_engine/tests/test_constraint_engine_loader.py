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


def test_loads_a_workshop_without_products_or_routings(make_plant: PlantWriter) -> None:
    extra = {
        "resources.csv": (
            "resource_code,name,station_code,kind,parallel_units\n"
            "FINISH,Finishing,PAINT,manual,3\nPACK,Packing,PAINT,manual,2\n"
        ),
        "orders.csv": (
            "order_id,sku,quantity_units,due_at,status,released_at,shipped_at,material_ready_at,"
            "order_value_eur_cents,material_cost_eur_cents\n"
            "J-1,,4,2026-10-20T16:00:00Z,released,,,,125000,40000\n"
        ),
        "calendar.csv": (
            "resource_code,kind,start_at,end_at,covered,positions\n"
            "FINISH,shift,2026-10-13T04:00:00Z,2026-10-13T12:30:00Z,false,2\n"
        ),
        "events.csv": (
            "event_id,event_type,at,resource_code,station_code,order_id,operation_seq,"
            "quantity_units,scrap_units,down_reason_code,scrap_reason_code\n"
            "e1,start,2026-10-13T07:15:00Z,FINISH,,J-1,,4,0,,\n"
            "e2,end,2026-10-13T09:50:00Z,FINISH,,J-1,,4,0,,\n"
        ),
        "teams.csv": "team_code,name,resource_codes\nFINISH-TEAM,Finishing,FINISH;PACK\n",
        "team_shifts.csv": (
            "team_code,start_at,end_at,positions\n"
            "FINISH-TEAM,2026-10-13T04:00:00Z,2026-10-13T12:30:00Z,3\n"
        ),
    }
    plant = load_plant(make_plant(skip=("products.csv", "routings.csv"), extra=extra))
    assert plant.row_errors == []
    assert plant.missing_files == {}
    assert [r.kind for r in plant.resources] == ["manual", "manual"]
    assert plant.orders[0].sku is None and plant.orders[0].order_value_eur_cents == 125000
    assert plant.calendar[0].positions == 2
    assert plant.teams[0].resource_codes == ("FINISH", "PACK")
    assert plant.team_shifts[0].positions == 3
