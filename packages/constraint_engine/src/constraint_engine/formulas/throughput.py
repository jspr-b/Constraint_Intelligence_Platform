"""Throughput accounting (CLAUDE.md, Domain model).

Throughput = sales price − truly variable cost. Not cost-accounting margin: labour and
overhead are not subtracted. Throughput per constraint minute ranks the product mix on the
constraint.
"""

from typing import Protocol

from constraint_engine.figure import Confidence, Figure, Missing
from constraint_engine.formulas.registry import Calc, Resolved, formula


class ProductCosts(Protocol):
    @property
    def sales_price_eur_cents(self) -> int | Missing: ...

    @property
    def truly_variable_cost_eur_cents(self) -> int | Missing: ...


@formula(
    "throughput_per_unit",
    1,
    "throughput per unit = sales price − truly variable cost",
    unit="eur_cents",
)
def throughput_per_unit_eur_cents(product: ProductCosts) -> Calc:
    def compute(i: Resolved) -> int:
        price, cost = i["sales_price_eur_cents"], i["truly_variable_cost_eur_cents"]
        assert isinstance(price, int) and isinstance(cost, int)
        return price - cost

    return Calc(
        inputs={
            "sales_price_eur_cents": product.sales_price_eur_cents,
            "truly_variable_cost_eur_cents": product.truly_variable_cost_eur_cents,
        },
        compute=compute,
    )


@formula(
    "throughput_per_constraint_min",
    1,
    "throughput per constraint minute = throughput per unit ÷ constraint minutes per unit",
    unit="eur_cents_per_min",
)
def throughput_per_constraint_min_eur_cents(
    product: ProductCosts, constraint_run_min_per_unit: float | Missing
) -> Calc:
    def compute(i: Resolved) -> float | Missing:
        minutes = float(i["constraint_run_min_per_unit"])
        if minutes <= 0:
            return Missing(
                what="constraint_run_min_per_unit",
                reason="product uses no constraint time; it does not compete for the constraint",
                confidence_impact=Confidence.NONE,
            )
        return float(i["throughput_per_unit"]) / minutes

    tpu: Figure = throughput_per_unit_eur_cents(product)
    return Calc(
        inputs={
            "throughput_per_unit": tpu,
            "constraint_run_min_per_unit": constraint_run_min_per_unit,
        },
        compute=compute,
    )
