"""€ to constraint hours (ADR-0007): same story, other unit; Missing when the rate is unknown."""

from datetime import UTC, datetime

import pytest

from constraint_engine.figure import Confidence, Figure, Missing
from constraint_engine.formulas.money import NO_RATE, to_constraint_hours

START, END = datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)
LOSS = Figure(
    value=4_100_000,
    unit="eur_cents",
    formula_id="test_v1",
    period_start_at=START,
    period_end_at=END,
)
RATE = Figure(value=205_000, unit="eur_cents_per_h", formula_id="test_rate_v1")


def test_converts_with_provenance() -> None:
    hours = to_constraint_hours(LOSS, RATE)
    assert hours.value == pytest.approx(20.0)
    assert hours.unit == "h" and hours.formula_id == "constraint_hours_v1"
    assert hours.inputs["amount_eur_cents"] is LOSS
    assert (hours.period_start_at, hours.period_end_at) == (START, END)


def test_unknown_rate_is_missing() -> None:
    hours = to_constraint_hours(LOSS, NO_RATE)
    assert isinstance(hours.value, Missing) and hours.confidence is Confidence.NONE


def test_zero_rate_is_missing() -> None:
    zero = Figure(value=0, unit="eur_cents_per_h", formula_id="test_rate_v1")
    assert isinstance(to_constraint_hours(LOSS, zero).value, Missing)


def test_rejects_wrong_units() -> None:
    with pytest.raises(ValueError, match="eur_cents"):
        to_constraint_hours(Figure(value=1, unit="h", formula_id="x_v1"), RATE)
    with pytest.raises(ValueError, match="eur_cents_per_h"):
        to_constraint_hours(LOSS, Figure(value=1, unit="eur_cents", formula_id="x_v1"))
