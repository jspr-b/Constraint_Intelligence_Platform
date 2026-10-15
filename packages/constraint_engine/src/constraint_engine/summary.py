"""Plant summary: what was loaded, as Figures (pure; no I/O)."""

from dataclasses import dataclass
from datetime import datetime

from constraint_engine.figure import Figure, Missing
from constraint_engine.formulas.registry import Calc, Resolved, formula
from constraint_engine.io.plant_loader import LoadedPlant


@formula("record_count", 1, "count of valid rows loaded for a record type", unit="rows")
def record_count(name: str, rows: int, rejected: int) -> Calc:
    def compute(i: Resolved) -> int:
        return int(i["valid_rows"])

    return Calc(
        inputs={"record_type": name, "valid_rows": rows, "rejected_rows": rejected}, compute=compute
    )


@dataclass(frozen=True, slots=True)
class PlantSummary:
    plant_name: str | None
    counts: dict[str, Figure]
    event_period_start_at: datetime | None
    event_period_end_at: datetime | None


COUNTED = {
    "resources": "resources.csv",
    "products": "products.csv",
    "orders": "orders.csv",
    "events": "events.csv",
}


def summarise(plant: LoadedPlant) -> PlantSummary:
    rejected = {f: 0 for f in COUNTED.values()}
    for err in plant.row_errors:
        if err.file in rejected:
            rejected[err.file] += 1
    counts = {
        name: record_count(name, len(getattr(plant, name)), rejected[file])
        for name, file in COUNTED.items()
    }
    times = [e.at for e in plant.events]
    name = None if isinstance(plant.plant, Missing) else plant.plant.name
    return PlantSummary(
        plant_name=name,
        counts=counts,
        event_period_start_at=min(times) if times else None,
        event_period_end_at=max(times) if times else None,
    )
