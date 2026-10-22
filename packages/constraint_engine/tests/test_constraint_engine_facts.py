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
    for period_kind in ("all", "month", "week"):
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
