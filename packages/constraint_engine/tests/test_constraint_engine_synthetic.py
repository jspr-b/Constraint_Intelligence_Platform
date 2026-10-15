from datetime import date, time
from pathlib import Path

import pytest

from constraint_engine.io.plant_loader import load_plant
from constraint_engine.synthetic.config import (
    PlantCfg,
    ProductCfg,
    ResourceCfg,
    ShiftCfg,
    StepCfg,
)
from constraint_engine.synthetic.model import simulate
from constraint_engine.synthetic.truth import STATES, machine_truth
from constraint_engine.synthetic.writer import write_plant


def two_machine_line(seed: int = 7, cv: float = 0.0) -> PlantCfg:
    """FAST-01 (2 min/unit) feeds SLOW-01 (6 min/unit); queue before SLOW-01 holds 3 orders."""
    return PlantCfg(
        plant_code="LINE-2",
        name="Two machine line",
        seed=seed,
        start_date=date(2026, 3, 2),
        weeks_history=4,
        weeks_orderbook=1,
        stations={"FAST": "Fast", "SLOW": "Slow"},
        resources=(
            ResourceCfg(code="FST-01", name="Fast", station="FAST"),
            ResourceCfg(code="SLW-01", name="Slow", station="SLOW", buffer_orders=3),
        ),
        shifts=(ShiftCfg(start=time(8, 0), end=time(16, 0)),),
        products=(
            ProductCfg(
                sku="P1",
                name="Part",
                family="Parts",
                setup_family="A",
                price_eur_cents=10000,
                tvc_eur_cents=4000,
                orders_per_week=60,
                qty_min=10,
                qty_max=10,
                steps=(
                    StepCfg(operation="Cut", resource="FST-01", run_min_per_unit=2, cv=cv),
                    StepCfg(operation="Finish", resource="SLW-01", run_min_per_unit=6, cv=cv),
                ),
            ),
        ),
    )


def test_output_matches_slow_machine_capacity() -> None:
    result = simulate(two_machine_line())
    week_min = 7 * 1440
    for week in (2, 3, 4):
        units = sum(
            q
            for at, q in result.logs["SLW-01"].units_out
            if (week - 1) * week_min <= at < week * week_min
        )
        # 5 days x 480 min / 6 min per unit = 400 units per week
        assert units == pytest.approx(400, rel=0.03)


def test_slow_machine_is_never_starved_and_fast_one_gets_blocked() -> None:
    result = simulate(two_machine_line())
    week = 7 * 1440.0
    slow = machine_truth(result, "SLW-01", (week, 4 * week))
    fast = machine_truth(result, "FST-01", (week, 4 * week))
    assert slow["starved_min"] == pytest.approx(0, abs=1)
    assert fast["blocked_min"] > 0.5 * fast["shift_min"]


@pytest.mark.parametrize("code", ["FST-01", "SLW-01"])
def test_every_shift_minute_is_accounted_for(code: str) -> None:
    result = simulate(two_machine_line(cv=0.3))
    t = machine_truth(result, code, (0.0, result.history_end))
    parts = sum(t[k] for k in STATES if k not in ("shift_min", "scrap_run_min"))
    assert parts == pytest.approx(t["shift_min"], abs=0.5)


def test_same_seed_same_plant_different_seed_different_plant() -> None:
    a = simulate(two_machine_line(seed=1, cv=0.3)).events
    b = simulate(two_machine_line(seed=1, cv=0.3)).events
    c = simulate(two_machine_line(seed=2, cv=0.3)).events
    assert a == b
    assert a != c


def test_written_plant_loads_without_errors(tmp_path: Path) -> None:
    root = write_plant(simulate(two_machine_line(cv=0.2)), tmp_path / "line")
    plant = load_plant(root)
    assert plant.row_errors == []
    assert plant.missing_files == {}
    assert len(plant.events) > 100
    assert (root / "generator_log.json").exists()
