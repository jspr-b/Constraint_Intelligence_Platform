"""Write and read a loaded plant as Parquet, for laptop diagnostics without a database."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import polars as pl
from pydantic import BaseModel

from cip_schema.master import (
    CalendarWindow,
    CapacityCost,
    Changeover,
    OutsourcingPrice,
    OvertimeWorked,
    Plant,
    Product,
    Resource,
    ResourceOperation,
    Routing,
    RoutingStep,
    Station,
    Team,
    TeamShift,
)
from cip_schema.transactional import OperationEvent, Order
from constraint_engine.figure import Confidence, Missing
from constraint_engine.io.plant_loader import LoadedPlant, RowError

RECORDS: dict[str, type[BaseModel]] = {
    "stations": Station,
    "resources": Resource,
    "products": Product,
    "orders": Order,
    "events": OperationEvent,
    "calendar": CalendarWindow,
    "resource_operations": ResourceOperation,
    "changeovers": Changeover,
    "overtime": OvertimeWorked,
    "capacity_costs": CapacityCost,
    "outsourcing": OutsourcingPrice,
    "teams": Team,
    "team_shifts": TeamShift,
}


def _plain(row: dict[str, Any]) -> dict[str, Any]:
    """Parquet-friendly values: UUIDs as text (validated back on read), timestamps kept typed."""
    return {k: str(v) if isinstance(v, UUID) else v for k, v in row.items()}


def to_parquet(plant: LoadedPlant, directory: Path | str) -> Path:
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    for name, model in RECORDS.items():
        rows = [_plain(r.model_dump(mode="python")) for r in getattr(plant, name)]
        frame = (
            pl.DataFrame(rows, infer_schema_length=None)
            if rows
            else pl.DataFrame(schema={f: pl.String for f in model.model_fields})
        )
        frame.write_parquet(out / f"{name}.parquet")
    steps = [
        {
            "tenant_id": str(r.tenant_id),
            "sku": r.sku,
            **s.model_dump(),
            "alternative_resource_codes": list(s.alternative_resource_codes),
        }
        for r in plant.routings
        for s in r.steps
    ]
    pl.DataFrame(steps, infer_schema_length=None).write_parquet(out / "routings.parquet")
    meta: dict[str, Any] = {
        "plant": None if isinstance(plant.plant, Missing) else plant.plant.model_dump(mode="json"),
        "row_errors": [
            {"file": e.file, "line": e.line, "reason": e.reason} for e in plant.row_errors
        ],
        "missing_files": {k: v.to_dict() for k, v in plant.missing_files.items()},
    }
    (out / "plant_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return out


def from_parquet(directory: Path | str) -> LoadedPlant:
    root = Path(directory)
    meta = json.loads((root / "plant_meta.json").read_text())
    plant = (
        Plant.model_validate(meta["plant"])
        if meta["plant"]
        else Missing("plant.json", "not in Parquet set")
    )
    loaded = LoadedPlant(plant=plant)
    for name, model in RECORDS.items():
        frame = pl.read_parquet(root / f"{name}.parquet")
        setattr(loaded, name, [model.model_validate(r) for r in frame.iter_rows(named=True)])
    by_sku: dict[tuple[Any, str], list[RoutingStep]] = {}
    for r in pl.read_parquet(root / "routings.parquet").iter_rows(named=True):
        tenant, sku = r.pop("tenant_id"), r.pop("sku")
        r["alternative_resource_codes"] = tuple(r["alternative_resource_codes"] or ())
        by_sku.setdefault((tenant, sku), []).append(RoutingStep.model_validate(r))
    loaded.routings = [
        Routing(tenant_id=t, sku=s, steps=tuple(steps)) for (t, s), steps in by_sku.items()
    ]
    loaded.row_errors = [RowError(**e) for e in meta["row_errors"]]
    loaded.missing_files = {
        k: Missing(v["missing"], v["reason"], Confidence[v["confidence_impact"].upper()])
        for k, v in meta["missing_files"].items()
    }
    return loaded
