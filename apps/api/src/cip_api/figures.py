"""API envelope for numbers: every numeric field is a FigureOut (ADR-0003)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from constraint_engine.figure import Figure


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
