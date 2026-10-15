"""Background jobs. Logs carry ids and counts, never plant data values (ADR-0005).

Run: ``uv run dramatiq cip_workers.actors``
"""

import logging
from typing import Any

import dramatiq

from cip_workers.broker import broker  # noqa: F401  (sets the broker before actors are declared)
from constraint_engine.io.plant_loader import load_plant
from constraint_engine.summary import summarise

log = logging.getLogger("cip.workers")


@dramatiq.actor(max_retries=0, store_results=True)
def ping() -> str:
    return "pong"


@dramatiq.actor(max_retries=1, store_results=True)
def diagnose_plant(plant_dir: str) -> dict[str, Any]:
    """Load a plant in the standard layout and return its summary as Figure dicts."""
    plant = load_plant(plant_dir)
    summary = summarise(plant)
    log.info(
        "diagnose_plant done",
        extra={
            "rows": sum(int(f.value) for f in summary.counts.values() if isinstance(f.value, int))
        },
    )
    return {
        "plant_name": summary.plant_name,
        "counts": {k: v.to_dict() for k, v in summary.counts.items()},
        "row_errors": len(plant.row_errors),
        "missing_files": sorted(plant.missing_files),
    }
