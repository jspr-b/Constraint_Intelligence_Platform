"""Formula registry: every calculation has an id, a version and its formula text (ADR-0003).

A formula function returns a :class:`Calc` (named inputs and a pure compute function). The
``@formula`` decorator turns that into a :class:`Figure`: missing inputs propagate as Missing,
confidence is the weakest input confidence, and the formula id is attached.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from typing import ParamSpec

from constraint_engine.figure import Confidence, Figure, Missing, first_missing, input_confidence

P = ParamSpec("P")
Inputs = Mapping[str, Figure | Missing | int | float | str]
Resolved = Mapping[str, int | float | str]


@dataclass(frozen=True, slots=True)
class FormulaSpec:
    name: str
    version: int
    text: str
    unit: str

    @property
    def formula_id(self) -> str:
        return f"{self.name}_v{self.version}"


@dataclass(frozen=True, slots=True)
class Calc:
    """What a formula function returns: its inputs and how to compute the value from them."""

    inputs: Inputs
    compute: Callable[[Resolved], int | float | Missing]
    period_start_at: datetime | None = None
    period_end_at: datetime | None = None
    confidence_cap: Confidence = Confidence.HIGH


@dataclass
class FormulaRegistry:
    _specs: dict[str, FormulaSpec] = field(default_factory=dict)

    def register(self, spec: FormulaSpec) -> None:
        if spec.formula_id in self._specs:
            raise ValueError(f"formula {spec.formula_id} is already registered")
        self._specs[spec.formula_id] = spec

    def get(self, formula_id: str) -> FormulaSpec:
        return self._specs[formula_id]

    def list(self) -> list[FormulaSpec]:
        return sorted(self._specs.values(), key=lambda s: s.formula_id)


registry = FormulaRegistry()


def _resolve(inputs: Inputs) -> dict[str, int | float | str]:
    out: dict[str, int | float | str] = {}
    for name, value in inputs.items():
        if isinstance(value, Figure):
            assert not isinstance(value.value, Missing)
            out[name] = value.value
        elif not isinstance(value, Missing):
            out[name] = value
    return out


def formula(
    name: str, version: int, text: str, unit: str, *, target: FormulaRegistry = registry
) -> Callable[[Callable[P, Calc]], Callable[P, Figure]]:
    """Register a formula and make the decorated function return a Figure."""
    spec = FormulaSpec(name=name, version=version, text=text, unit=unit)
    target.register(spec)

    def decorate(fn: Callable[P, Calc]) -> Callable[P, Figure]:
        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Figure:
            calc = fn(*args, **kwargs)
            missing = first_missing(calc.inputs)
            value: int | float | Missing = (
                missing if missing is not None else calc.compute(_resolve(calc.inputs))
            )
            confidence = min(
                input_confidence(calc.inputs), calc.confidence_cap, key=lambda c: c.value
            )
            return Figure(
                value=value,
                unit=spec.unit,
                formula_id=spec.formula_id,
                inputs=dict(calc.inputs),
                period_start_at=calc.period_start_at,
                period_end_at=calc.period_end_at,
                confidence=confidence,
            )

        return wrapper

    return decorate
