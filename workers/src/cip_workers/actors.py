"""Background jobs. Logs carry ids and counts, never plant data values (ADR-0005).

Run: ``uv run dramatiq cip_workers.actors``
"""

import logging
import uuid
from typing import Any

import dramatiq

from cip_api.facts import compute_facts as compute_facts_job
from cip_api.imports import run_import as run_import_job
from cip_api.settings import get_settings
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


@dramatiq.actor(max_retries=0, store_results=True)
def run_import(tenant_id: str, import_id: str) -> None:
    """Run an uploaded import (cip_api.imports.run_import). Logs ids only."""
    run_import_job(get_settings(), uuid.UUID(tenant_id), uuid.UUID(import_id))
    log.info("run_import done", extra={"import_id": import_id})


@dramatiq.actor(max_retries=0, store_results=True)
def compute_facts(tenant_id: str, import_id: str) -> None:
    """Calculate the plant's measured facts from a finished import. Logs ids and counts only."""
    count = compute_facts_job(get_settings(), uuid.UUID(tenant_id), uuid.UUID(import_id))
    log.info("compute_facts done", extra={"import_id": import_id, "facts": count})
