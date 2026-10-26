"""Numbers that use rows fixed in the app say so (ADR-0010 point 7).

A fixed touchpoint counts for every number whose period holds it; a line left out or a row
removed on Setup or Calendar counts for every number. When the fixed rows are a large share of
the touchpoints in the period, the number is less certain: its confidence drops one level
(not below low).
"""

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from constraint_engine.figure import Confidence, Figure

LARGE_SHARE = 0.10
"""Fixed rows at or above this share of the period's touchpoints lower the confidence."""


def with_fixed_rows(
    figure: Figure,
    fixed_at: Sequence[datetime],
    fixed_anywhere: int,
    events_at: Sequence[datetime],
) -> Figure:
    """``figure`` with ``fixed_rows`` among its inputs, or unchanged when it uses none.

    ``fixed_at`` and ``events_at`` must be sorted. Inputs added: ``fixed_rows`` (count) and,
    when fixed rows / touchpoints in the period >= 10 %, ``fixed_rows_share_pct``.
    """
    start, end = figure.period_start_at, figure.period_end_at

    def within(times: Sequence[datetime]) -> int:
        lo = 0 if start is None else bisect_left(times, start)
        hi = len(times) if end is None else bisect_right(times, end)
        return max(0, hi - lo)

    fixed = within(fixed_at) + fixed_anywhere
    if fixed == 0:
        return figure
    inputs = {**figure.inputs, "fixed_rows": fixed}
    confidence = figure.confidence
    events = within(events_at)
    if events and fixed / events >= LARGE_SHARE:
        inputs["fixed_rows_share_pct"] = round(100 * fixed / events, 1)
        # At most down to LOW: NONE means a value is missing, which fixed rows do not make.
        if confidence.value > Confidence.LOW.value:
            confidence = Confidence(confidence.value - 1)
    return replace(figure, inputs=inputs, confidence=confidence)
