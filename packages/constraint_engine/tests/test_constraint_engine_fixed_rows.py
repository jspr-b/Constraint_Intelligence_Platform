"""Numbers say when they use rows fixed in the app (ADR-0010 point 7)."""

from datetime import UTC, datetime, timedelta

from constraint_engine.figure import Confidence, Figure
from constraint_engine.fixed_rows import with_fixed_rows

T0 = datetime(2026, 9, 1, tzinfo=UTC)
EVENTS = [T0 + timedelta(hours=h) for h in range(100)]
WEEK = Figure(10.0, "h", "x_v1", {}, T0, T0 + timedelta(hours=49), Confidence.HIGH)


def test_no_fixed_rows_leaves_the_number_as_it_is() -> None:
    assert with_fixed_rows(WEEK, [], 0, EVENTS) is WEEK


def test_fixed_rows_in_the_period_are_counted_and_others_not() -> None:
    marked = with_fixed_rows(WEEK, [T0 + timedelta(hours=3), T0 + timedelta(hours=80)], 0, EVENTS)
    assert marked.inputs["fixed_rows"] == 1
    assert "fixed_rows_share_pct" not in marked.inputs and marked.confidence is Confidence.HIGH
    assert with_fixed_rows(WEEK, [T0 + timedelta(hours=80)], 0, EVENTS) is WEEK


def test_rows_left_out_count_for_every_number() -> None:
    assert with_fixed_rows(WEEK, [], 2, EVENTS).inputs["fixed_rows"] == 2


def test_a_large_share_of_fixed_rows_lowers_confidence_one_level() -> None:
    fixed = [T0 + timedelta(hours=h) for h in range(5)]  # 5 of 50 touchpoints = 10 %
    marked = with_fixed_rows(WEEK, fixed, 0, EVENTS)
    assert marked.inputs["fixed_rows_share_pct"] == 10.0
    assert marked.confidence is Confidence.MEDIUM
    whole = Figure(1.0, "h", "x_v1", {}, None, None, Confidence.LOW)
    assert with_fixed_rows(whole, fixed, 6, EVENTS).confidence is Confidence.LOW  # 11 of 100
    assert with_fixed_rows(whole, fixed, 6, EVENTS).inputs["fixed_rows_share_pct"] == 11.0
