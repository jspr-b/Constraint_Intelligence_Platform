import json
from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from constraint_engine.figure import (
    Confidence,
    Figure,
    Missing,
    first_missing,
    input_confidence,
    weakest,
)

START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 30, 23, 59, tzinfo=UTC)


def leaf(value: float, confidence: Confidence = Confidence.HIGH) -> Figure:
    return Figure(value=value, unit="h", formula_id="leaf_v1", confidence=confidence)


def test_nested_explain_shows_formula_and_inputs() -> None:
    hours = leaf(22.0)
    fig = Figure(
        value=4_070_000,
        unit="eur_cents",
        formula_id="loss_eur_v1",
        inputs={"lost_constraint_h": hours, "throughput_eur_cents_per_h": 185_000},
        period_start_at=START,
        period_end_at=END,
    )
    text = fig.explain()
    assert text.splitlines()[0] == "loss_eur_v1 = 4070000 eur_cents (confidence high)"
    assert "lost_constraint_h:" in text
    assert "    leaf_v1 = 22.0 h" in text
    assert "throughput_eur_cents_per_h: 185000" in text


def test_to_dict_is_json_serialisable() -> None:
    fig = Figure(
        value=1,
        unit="units",
        formula_id="x_v1",
        inputs={"a": leaf(1.0), "b": Missing("b", "not exported")},
        period_start_at=START,
    )
    data = json.loads(json.dumps(fig.to_dict()))
    assert data["inputs"]["a"]["formula_id"] == "leaf_v1"
    assert data["inputs"]["b"] == {
        "missing": "b",
        "reason": "not exported",
        "confidence_impact": "high",
    }
    assert data["period_start_at"] == "2026-09-01T00:00:00+00:00"


def test_missing_value_forces_no_confidence() -> None:
    fig = Figure(value=Missing("price", "no products file"), unit="eur_cents", formula_id="x_v1")
    assert fig.is_missing
    assert fig.confidence is Confidence.NONE
    assert "MISSING" not in fig.explain() and "no products file" in fig.explain()


def test_first_missing_finds_direct_and_nested() -> None:
    assert first_missing({"a": 1, "b": leaf(2.0)}) is None
    direct = first_missing({"a": Missing("a", "gap")})
    assert direct is not None and direct.what == "a"
    nested = Figure(value=Missing("tvc", "no cost"), unit="eur_cents", formula_id="t_v1")
    found = first_missing({"throughput": nested})
    assert found is not None and found.what == "throughput (tvc)"


@given(st.lists(st.sampled_from(list(Confidence)), min_size=1))
def test_weakest_is_minimum(values: list[Confidence]) -> None:
    assert weakest(values).value == min(v.value for v in values)


def test_input_confidence_ignores_plain_values() -> None:
    assert input_confidence({"a": 1, "b": leaf(1.0, Confidence.LOW)}) is Confidence.LOW
    assert input_confidence({"a": 1}) is Confidence.HIGH


def test_period_must_be_aware_and_ordered() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Figure(value=1, unit="h", formula_id="x", period_start_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="before"):
        Figure(value=1, unit="h", formula_id="x", period_start_at=END, period_end_at=START)
