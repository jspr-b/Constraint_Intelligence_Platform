from dataclasses import dataclass

import pytest

from constraint_engine.figure import Confidence, Figure, Missing
from constraint_engine.formulas import registry
from constraint_engine.formulas.registry import Calc, FormulaRegistry, formula
from constraint_engine.formulas.throughput import (
    throughput_per_constraint_min_eur_cents,
    throughput_per_unit_eur_cents,
)


@dataclass(frozen=True)
class P:
    sales_price_eur_cents: int | Missing
    truly_variable_cost_eur_cents: int | Missing


FRAME = P(98000, 43000)  # synthetic plant_a Frame F-200
COVER = P(21000, 9500)


def test_throughput_per_unit_known_answers() -> None:
    fig = throughput_per_unit_eur_cents(FRAME)
    assert fig.value == 55000
    assert fig.formula_id == "throughput_per_unit_v1"
    assert fig.unit == "eur_cents"
    assert fig.inputs == {"sales_price_eur_cents": 98000, "truly_variable_cost_eur_cents": 43000}


def test_negative_throughput_is_allowed() -> None:
    assert throughput_per_unit_eur_cents(P(1000, 1500)).value == -500


def test_missing_cost_propagates() -> None:
    fig = throughput_per_unit_eur_cents(P(98000, Missing("tvc", "not in products export")))
    assert fig.is_missing
    assert fig.confidence is Confidence.NONE
    assert isinstance(fig.value, Missing) and fig.value.reason == "not in products export"


def test_throughput_per_constraint_minute_ranks_mix() -> None:
    frame = throughput_per_constraint_min_eur_cents(FRAME, 16.5)
    cover = throughput_per_constraint_min_eur_cents(COVER, 4.5)
    assert frame.value == pytest.approx(3333.33, abs=0.01)
    assert cover.value == pytest.approx(2555.56, abs=0.01)
    assert isinstance(frame.value, float) and isinstance(cover.value, float)
    assert frame.value > cover.value
    assert isinstance(frame.inputs["throughput_per_unit"], Figure)


def test_zero_constraint_time_is_missing_not_division_error() -> None:
    rail = throughput_per_constraint_min_eur_cents(P(16000, 7000), 0)
    assert isinstance(rail.value, Missing)
    assert "no constraint time" in rail.value.reason


def test_registry_lists_formulas() -> None:
    ids = [s.formula_id for s in registry.list()]
    assert "throughput_per_unit_v1" in ids and "throughput_per_constraint_min_v1" in ids
    assert registry.get("throughput_per_unit_v1").text.startswith("throughput per unit")


def test_duplicate_registration_rejected() -> None:
    local = FormulaRegistry()

    @formula("x", 1, "x = 1", unit="units", target=local)
    def x() -> Calc:
        return Calc(inputs={}, compute=lambda i: 1)

    assert x().value == 1
    with pytest.raises(ValueError, match="already registered"):
        formula("x", 1, "x = 1", unit="units", target=local)
