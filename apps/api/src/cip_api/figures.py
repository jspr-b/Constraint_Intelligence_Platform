"""API envelope for numbers: every numeric field is a FigureOut (ADR-0003)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from constraint_engine.figure import Figure, Missing
from constraint_engine.formulas.money import NO_RATE, to_constraint_hours


class MissingOut(BaseModel):
    missing: str
    reason: str
    confidence_impact: str


class FigureOut(BaseModel):
    """A number with its unit, formula, inputs, data period and confidence."""

    value: float | int | MissingOut
    unit: str
    formula_id: str
    inputs: dict[str, Any]
    period_start_at: datetime | None
    period_end_at: datetime | None
    confidence: str

    @classmethod
    def from_figure(cls, figure: Figure) -> FigureOut:
        return cls.model_validate(figure.to_dict())


def money_out(
    amount: Figure, money: str, throughput_per_constraint_h: Figure | Missing = NO_RATE
) -> FigureOut:
    """A € Figure as the role may see it: € as is, or constraint hours via the engine (ADR-0007).

    The conversion is the engine's ``to_constraint_hours``; the API does no arithmetic. Until a
    constraint is detected the rate is unknown, so hours show as Missing, never as a guess.
    """
    if money == "hours":
        return FigureOut.from_figure(to_constraint_hours(amount, throughput_per_constraint_h))
    return FigureOut.from_figure(amount)
