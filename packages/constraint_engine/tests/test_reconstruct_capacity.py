"""OEE and effective capacity on a one-machine plant computed by hand."""

import json
from pathlib import Path

import pytest

from constraint_engine.figure import Confidence
from constraint_engine.io.plant_loader import load_plant
from constraint_engine.reconstruct.capacity import machine_oee

HEADER = ",".join(
    (
        "event_id",
        "event_type",
        "at",
        "resource_code",
        "station_code",
        "order_id",
        "operation_seq",
        "quantity_units",
        "scrap_units",
        "down_reason_code",
        "scrap_reason_code",
    )
)
EVENTS = (
    HEADER
    + """
e1,start,2026-10-13T06:00:00Z,PNT-01,,SO-1,10,10,0,,
e2,end,2026-10-13T07:40:00Z,PNT-01,,SO-1,10,10,0,,
e3,start,2026-10-13T08:00:00Z,PNT-01,,SO-2,10,20,0,,
e4,end,2026-10-13T10:50:00Z,PNT-01,,SO-2,10,20,0,,
e5,scrap,2026-10-13T10:50:00Z,PNT-01,,SO-2,10,0,2,,QUALITY
e6,down_start,2026-10-13T12:00:00Z,PNT-01,,,,0,0,MECH,
e7,down_end,2026-10-13T12:30:00Z,PNT-01,,,,0,0,MECH,
"""
)


def tiny_plant(root: Path, std: str = "6") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "plant.json").write_text(
        json.dumps({"plant_code": "T", "name": "Tiny", "timezone_iana": "UTC"})
    )
    (root / "stations.csv").write_text("station_code,name\nPAINT,Paint\n")
    (root / "resources.csv").write_text(
        "resource_code,name,station_code\nPNT-01,Paint line,PAINT\n"
    )
    (root / "products.csv").write_text(
        "sku,name,family,sales_price_eur_cents,truly_variable_cost_eur_cents\nP,Part,Parts,1000,400\n"
    )
    (root / "routings.csv").write_text(
        f"sku,operation_seq,operation,resource_code,standard_run_min_per_unit\nP,10,Paint,PNT-01,{std}\n"
    )
    (root / "orders.csv").write_text(
        "order_id,sku,quantity_units,due_at\nSO-1,P,10,2026-10-20T00:00:00Z\nSO-2,P,20,2026-10-20T00:00:00Z\n"
    )
    (root / "events.csv").write_text(EVENTS)
    (root / "calendar.csv").write_text(
        "resource_code,kind,start_at,end_at,covered\n"
        "PNT-01,shift,2026-10-13T06:00:00Z,2026-10-13T14:00:00Z,false\n"
        "PNT-01,break,2026-10-13T10:00:00Z,2026-10-13T10:30:00Z,false\n"
    )
    return root


def test_oee_by_hand(tmp_path: Path) -> None:
    result = machine_oee(load_plant(tiny_plant(tmp_path / "p")))["PNT-01"]
    # planned 480 - 30 break = 450; stop 30 -> run time 420
    assert result.availability.value == pytest.approx(420 / 450, abs=1e-4)
    # ideal 6 min x 30 units = 180 over 420 minutes
    assert result.performance.value == pytest.approx(180 / 420, abs=1e-4)
    # 2 of 30 units scrapped
    assert result.quality.value == pytest.approx(28 / 30, abs=1e-4)
    assert result.oee.value == pytest.approx(0.3733, abs=1e-4)
    assert result.oee.formula_id == "oee_v1"
    # effective capacity: 450 min = 7.5 h x 0.9333 = 7.0 h
    assert result.effective_capacity_h.value == pytest.approx(7.0, abs=1e-3)
    assert "availability" in result.oee.explain()


def test_missing_standard_falls_back_to_measured_with_low_confidence(tmp_path: Path) -> None:
    result = machine_oee(load_plant(tiny_plant(tmp_path / "p", std="")))["PNT-01"]
    assert result.performance.inputs["ideal_source"] == "measured"
    assert result.performance.confidence is Confidence.LOW
    assert result.oee.confidence is Confidence.LOW


def test_plant_a_paint_line_is_the_busiest() -> None:
    data = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "plant_a"
    results = machine_oee(load_plant(data))
    perf = {code: r.performance.value for code, r in results.items()}
    assert max(perf, key=lambda c: float(perf[c])) == "PNT-01"  # type: ignore[arg-type]
