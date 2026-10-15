"""Money shown as constraint hours, for roles that see hours instead of € (ADR-0007).

constraint hours = € amount ÷ throughput per constraint hour. One constraint hour is worth the
throughput the plant earns in it, so both views tell the same story.
"""

from constraint_engine.figure import Confidence, Figure, Missing
from constraint_engine.formulas.registry import Calc, Resolved, formula

NO_RATE = Missing(
    what="throughput_per_constraint_h_eur_cents",
    reason="throughput per constraint hour is not known yet (needs a detected constraint)",
    confidence_impact=Confidence.NONE,
)


@formula(
    "constraint_hours",
    1,
    "constraint hours = € amount ÷ throughput per constraint hour",
    unit="h",
)
def to_constraint_hours(amount: Figure, throughput_per_constraint_h: Figure | Missing) -> Calc:
    """Convert a € Figure (EUR cents) to constraint hours; Missing when the rate is unknown."""
    if amount.unit != "eur_cents":
        raise ValueError(f"expected an amount in eur_cents, got {amount.unit}")
    if isinstance(throughput_per_constraint_h, Figure) and (
        throughput_per_constraint_h.unit != "eur_cents_per_h"
    ):
        raise ValueError(
            f"expected a rate in eur_cents_per_h, got {throughput_per_constraint_h.unit}"
        )

    def compute(i: Resolved) -> float | Missing:
        rate = float(i["throughput_per_constraint_h_eur_cents"])
        if rate <= 0:
            return Missing(
                what="throughput_per_constraint_h_eur_cents",
                reason="throughput per constraint hour is zero or negative",
                confidence_impact=Confidence.NONE,
            )
        return float(i["amount_eur_cents"]) / rate

    return Calc(
        inputs={
            "amount_eur_cents": amount,
            "throughput_per_constraint_h_eur_cents": throughput_per_constraint_h,
        },
        compute=compute,
        period_start_at=amount.period_start_at,
        period_end_at=amount.period_end_at,
    )
