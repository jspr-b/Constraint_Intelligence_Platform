"""Measured facts match what the synthetic plants were built to produce (known answers)."""

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from constraint_engine.facts import Fact, measured_facts
from constraint_engine.figure import Confidence
from constraint_engine.io.plant_loader import load_plant
from constraint_engine.reconstruct.states import STATES, UNKNOWN

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "synthetic"


def _utilisation(facts: list[Fact]) -> dict[str, Fact]:
    return {
        f.subject_code: f
        for f in facts
        if f.measure == "utilisation_pct" and f.period_kind == "all"
    }


def _expected(plant: str) -> dict[str, float]:
    answers = yaml.safe_load((DATA / plant / "expected_answers.yaml").read_text())
    return dict(answers["utilisation_pct"])


@pytest.fixture(scope="module")
def facts_a() -> list[Fact]:
    return measured_facts(load_plant(DATA / "plant_a"))


@pytest.mark.parametrize("plant", ["plant_a", "plant_b", "plant_c"])
def test_utilisation_matches_the_known_answers(plant: str) -> None:
    got = _utilisation(measured_facts(load_plant(DATA / plant)))
    for code, want in _expected(plant).items():
        assert got[code].figure.value == pytest.approx(want, abs=0.1), (plant, code)
        assert got[code].figure.confidence is Confidence.HIGH


def test_every_shift_minute_is_one_state(facts_a: list[Fact]) -> None:
    for period_kind in ("all", "month", "week", "day"):
        sums: dict[tuple[str, datetime | None], float] = {}
        shift: dict[tuple[str, datetime | None], float] = {}
        for f in facts_a:
            if f.family != "state" or f.period_kind != period_kind:
                continue
            key = (f.subject_code, f.figure.period_start_at)
            value = float(f.figure.value)  # type: ignore[arg-type]
            if f.measure == "shift_min":
                shift[key] = value
            elif f.measure.removesuffix("_min") in (*STATES, UNKNOWN):
                sums[key] = sums.get(key, 0.0) + value
        assert shift and sums.keys() == shift.keys()
        for key, total in sums.items():
            assert total == pytest.approx(shift[key], abs=0.5), (period_kind, key)


def test_every_fact_has_a_period_and_a_registered_formula(facts_a: list[Fact]) -> None:
    from constraint_engine.formulas.registry import registry

    for f in facts_a:
        assert f.figure.period_start_at and f.figure.period_end_at, f
        registry.get(f.figure.formula_id)
    families = {f.family for f in facts_a}
    assert families == {
        "state",
        "state_share",
        "down_reason",
        "utilisation",
        "setup_share",
        "oee",
        "effective_capacity",
        "queue",
        "wip",
        "task_time",
    }


def test_the_same_plant_gives_the_same_facts(facts_a: list[Fact]) -> None:
    again = measured_facts(load_plant(DATA / "plant_a"))
    assert [f.figure.to_dict() for f in again] == [f.figure.to_dict() for f in facts_a]


def test_down_minutes_by_reason_add_up_to_the_down_state(facts_a: list[Fact]) -> None:
    down = {
        f.subject_code: float(f.figure.value)  # type: ignore[arg-type]
        for f in facts_a
        if f.measure == "down_min" and f.family == "state" and f.period_kind == "all"
    }
    by_reason: dict[str, float] = {}
    for f in facts_a:
        if f.family == "down_reason":
            assert f.reason_code
            by_reason[f.subject_code] = by_reason.get(f.subject_code, 0.0) + float(f.figure.value)  # type: ignore[arg-type]
    assert by_reason
    for code, minutes in by_reason.items():
        assert minutes == pytest.approx(down[code], abs=0.5), code


def test_state_shares_of_the_shift_add_up_to_100(facts_a: list[Fact]) -> None:
    shares: dict[str, float] = {}
    for f in facts_a:
        if f.family == "state_share" and f.period_kind == "all":
            shares[f.subject_code] = shares.get(f.subject_code, 0.0) + float(f.figure.value)  # type: ignore[arg-type]
    assert len(shares) == 6
    for code, total in shares.items():
        assert total == pytest.approx(100, abs=0.1), code


def test_days_carry_only_the_state_timeline(facts_a: list[Fact]) -> None:
    days = [f for f in facts_a if f.period_kind == "day"]
    assert days and {f.family for f in days} == {"state"}
