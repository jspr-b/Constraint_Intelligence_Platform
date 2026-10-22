"""Numbers that carry their own provenance (ADR-0003).

Every number the engine produces is a :class:`Figure`: value, unit, formula, inputs, period and
confidence. Missing data is a :class:`Missing`, never a default value.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

JsonValue = Any


class Confidence(Enum):
    """How much a number can be trusted. Ordered: NONE < LOW < MEDIUM < HIGH."""

    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @property
    def label(self) -> str:
        return self.name.lower()


def weakest(confidences: Iterable[Confidence]) -> Confidence:
    """The lowest confidence among inputs; HIGH when there are none."""
    return min(confidences, key=lambda c: c.value, default=Confidence.HIGH)


@dataclass(frozen=True, slots=True)
class Missing:
    """A value that is not available, with the reason and what it does to confidence."""

    what: str
    reason: str
    confidence_impact: Confidence = Confidence.HIGH

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "missing": self.what,
            "reason": self.reason,
            "confidence_impact": self.confidence_impact.label,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, JsonValue]) -> Missing:
        return cls(
            what=str(data["missing"]),
            reason=str(data["reason"]),
            confidence_impact=Confidence[str(data["confidence_impact"]).upper()],
        )


@dataclass(frozen=True, slots=True)
class Figure:
    """A computed number with everything needed to trace it."""

    value: int | float | Missing
    unit: str
    formula_id: str
    inputs: Mapping[str, Figure | Missing | int | float | str] = field(default_factory=dict)
    period_start_at: datetime | None = None
    period_end_at: datetime | None = None
    confidence: Confidence = Confidence.HIGH

    def __post_init__(self) -> None:
        for name, moment in (
            ("period_start_at", self.period_start_at),
            ("period_end_at", self.period_end_at),
        ):
            if moment is not None and moment.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware (ADR-0002)")
        if (
            self.period_start_at
            and self.period_end_at
            and self.period_end_at < self.period_start_at
        ):
            raise ValueError("period_end_at is before period_start_at")
        if isinstance(self.value, Missing) and self.confidence is not Confidence.NONE:
            object.__setattr__(self, "confidence", Confidence.NONE)

    @property
    def is_missing(self) -> bool:
        return isinstance(self.value, Missing)

    def explain(self, indent: int = 0) -> str:
        """Readable trace: the formula, then every input, nested Figures indented."""
        pad = "  " * indent
        shown = self.value.to_dict() if isinstance(self.value, Missing) else self.value
        lines = [
            f"{pad}{self.formula_id} = {shown} {self.unit} (confidence {self.confidence.label})"
        ]
        for name, value in self.inputs.items():
            if isinstance(value, Figure):
                lines.append(f"{pad}  {name}:")
                lines.append(value.explain(indent + 2))
            elif isinstance(value, Missing):
                lines.append(f"{pad}  {name}: MISSING ({value.reason})")
            else:
                lines.append(f"{pad}  {name}: {value}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, JsonValue]:
        """JSON-ready form used by the API envelope."""

        def enc(v: Figure | Missing | int | float | str) -> JsonValue:
            return v.to_dict() if isinstance(v, Figure | Missing) else v

        return {
            "value": enc(self.value),
            "unit": self.unit,
            "formula_id": self.formula_id,
            "inputs": {k: enc(v) for k, v in self.inputs.items()},
            "period_start_at": self.period_start_at.isoformat() if self.period_start_at else None,
            "period_end_at": self.period_end_at.isoformat() if self.period_end_at else None,
            "confidence": self.confidence.label,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, JsonValue]) -> Figure:
        return figure_from_dict(data)


def _decode(v: JsonValue) -> Figure | Missing | int | float | str:
    if isinstance(v, Mapping) and "formula_id" in v:
        return Figure.from_dict(v)
    if isinstance(v, Mapping) and "missing" in v:
        return Missing.from_dict(v)
    return v  # type: ignore[no-any-return]


def _moment(v: JsonValue) -> datetime | None:
    return datetime.fromisoformat(v) if isinstance(v, str) else v


def figure_from_dict(data: Mapping[str, JsonValue]) -> Figure:
    """The inverse of :meth:`Figure.to_dict`: a stored envelope back as a Figure."""
    value = _decode(data["value"])
    assert not isinstance(value, Figure | str)
    return Figure(
        value=value,
        unit=str(data["unit"]),
        formula_id=str(data["formula_id"]),
        inputs={k: _decode(v) for k, v in dict(data.get("inputs") or {}).items()},
        period_start_at=_moment(data.get("period_start_at")),
        period_end_at=_moment(data.get("period_end_at")),
        confidence=Confidence[str(data["confidence"]).upper()],
    )


def first_missing(inputs: Mapping[str, Figure | Missing | int | float | str]) -> Missing | None:
    """The first missing input (directly or inside a Figure), or None when all are present."""
    for name, value in inputs.items():
        if isinstance(value, Missing):
            return Missing(
                what=name, reason=value.reason, confidence_impact=value.confidence_impact
            )
        if isinstance(value, Figure) and isinstance(value.value, Missing):
            m = value.value
            return Missing(
                what=f"{name} ({m.what})", reason=m.reason, confidence_impact=m.confidence_impact
            )
    return None


def input_confidence(inputs: Mapping[str, Figure | Missing | int | float | str]) -> Confidence:
    """Weakest confidence among Figure inputs."""
    return weakest(v.confidence for v in inputs.values() if isinstance(v, Figure))
