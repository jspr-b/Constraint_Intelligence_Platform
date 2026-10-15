"""Load a plant directory in the standard layout (docs/plant_layout.md)."""

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import polars as pl
from pydantic import BaseModel, ValidationError

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
)
from cip_schema.transactional import OperationEvent, Order
from constraint_engine.figure import Confidence, Missing

OFFLINE_TENANT = uuid5(NAMESPACE_URL, "cip:offline")

REQUIRED = (
    "plant.json",
    "stations.csv",
    "resources.csv",
    "products.csv",
    "routings.csv",
    "orders.csv",
    "events.csv",
    "calendar.csv",
)


@dataclass(frozen=True, slots=True)
class RowError:
    file: str
    line: int
    reason: str


@dataclass
class LoadedPlant:
    plant: Plant | Missing
    stations: list[Station] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    products: list[Product] = field(default_factory=list)
    routings: list[Routing] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    events: list[OperationEvent] = field(default_factory=list)
    calendar: list[CalendarWindow] = field(default_factory=list)
    resource_operations: list[ResourceOperation] = field(default_factory=list)
    changeovers: list[Changeover] = field(default_factory=list)
    overtime: list[OvertimeWorked] = field(default_factory=list)
    capacity_costs: list[CapacityCost] = field(default_factory=list)
    outsourcing: list[OutsourcingPrice] = field(default_factory=list)
    row_errors: list[RowError] = field(default_factory=list)
    missing_files: dict[str, Missing] = field(default_factory=dict)

    def frame(self, name: str) -> pl.DataFrame:
        """A Polars frame of one record list, e.g. ``frame("events")``."""
        rows: list[BaseModel] = getattr(self, name)
        if name == "routings":
            flat = [
                {"sku": r.sku, **s.model_dump(exclude={"alternative_resource_codes"})}
                for r in self.routings
                for s in r.steps
            ]
            return pl.DataFrame(flat)
        return pl.DataFrame([r.model_dump(mode="python") for r in rows])


def _clean(row: dict[str, str]) -> dict[str, Any]:
    """Empty cells mean 'not given'."""
    return {k.strip(): (v.strip() if v.strip() != "" else None) for k, v in row.items() if k}


def _reason(exc: ValidationError) -> str:
    first = exc.errors()[0]
    loc = ".".join(str(p) for p in first["loc"]) or "row"
    return f"{loc}: {first['msg']}"


def _read_csv(path: Path) -> list[tuple[int, dict[str, Any]]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [(i + 2, _clean(row)) for i, row in enumerate(csv.DictReader(fh))]


def _load_rows[M: BaseModel](
    path: Path, model: type[M], tenant_id: UUID, plant: LoadedPlant
) -> list[M]:
    out: list[M] = []
    for line, row in _read_csv(path):
        values = {k: v for k, v in row.items() if v is not None}
        try:
            out.append(model.model_validate({"tenant_id": tenant_id, **values}))
        except ValidationError as exc:
            plant.row_errors.append(RowError(path.name, line, _reason(exc)))
    return out


def _load_routings(path: Path, tenant_id: UUID, plant: LoadedPlant) -> list[Routing]:
    steps: dict[str, list[RoutingStep]] = defaultdict(list)
    for line, row in _read_csv(path):
        values = {k: v for k, v in row.items() if v is not None}
        sku = values.pop("sku", None)
        alts = values.pop("alternative_resource_codes", None)
        try:
            if sku is None:
                raise ValueError("sku: Field required")
            step = RoutingStep.model_validate(
                {
                    **values,
                    "alternative_resource_codes": tuple(a for a in (alts or "").split(";") if a),
                }
            )
        except (ValidationError, ValueError) as exc:
            reason = _reason(exc) if isinstance(exc, ValidationError) else str(exc)
            plant.row_errors.append(RowError(path.name, line, reason))
            continue
        steps[sku].append(step)
    routings: list[Routing] = []
    for sku, sku_steps in steps.items():
        try:
            routings.append(
                Routing(
                    tenant_id=tenant_id,
                    sku=sku,
                    steps=tuple(sorted(sku_steps, key=lambda s: s.operation_seq)),
                )
            )
        except ValidationError as exc:
            plant.row_errors.append(RowError(path.name, 0, f"routing {sku}: {_reason(exc)}"))
    return routings


_FILES: dict[str, tuple[str, type[BaseModel]]] = {
    "stations.csv": ("stations", Station),
    "resources.csv": ("resources", Resource),
    "products.csv": ("products", Product),
    "orders.csv": ("orders", Order),
    "events.csv": ("events", OperationEvent),
    "calendar.csv": ("calendar", CalendarWindow),
    "resource_operations.csv": ("resource_operations", ResourceOperation),
    "changeovers.csv": ("changeovers", Changeover),
    "overtime.csv": ("overtime", OvertimeWorked),
    "capacity_costs.csv": ("capacity_costs", CapacityCost),
    "outsourcing.csv": ("outsourcing", OutsourcingPrice),
}


def load_plant(directory: Path | str, tenant_id: UUID = OFFLINE_TENANT) -> LoadedPlant:
    """Read every file of the standard layout. Never raises on bad or missing data."""
    root = Path(directory)
    plant_file = root / "plant.json"
    plant_value: Plant | Missing
    loaded = LoadedPlant(plant=Missing("plant.json", "not loaded yet"))
    if plant_file.exists():
        try:
            plant_value = Plant.model_validate(
                {"tenant_id": tenant_id, **json.loads(plant_file.read_text())}
            )
        except (ValidationError, json.JSONDecodeError) as exc:
            reason = (
                _reason(exc) if isinstance(exc, ValidationError) else f"invalid JSON: {exc.msg}"
            )
            loaded.row_errors.append(RowError("plant.json", 1, reason))
            plant_value = Missing("plant.json", "invalid plant.json", Confidence.HIGH)
    else:
        plant_value = Missing("plant.json", "file not found", Confidence.HIGH)
        loaded.missing_files["plant.json"] = plant_value
    loaded.plant = plant_value

    for name in REQUIRED[1:]:
        if not (root / name).exists():
            loaded.missing_files[name] = Missing(name, "file not found", Confidence.HIGH)

    for name, (attr, model) in _FILES.items():
        path = root / name
        if path.exists():
            setattr(loaded, attr, _load_rows(path, model, tenant_id, loaded))
    if (root / "routings.csv").exists():
        loaded.routings = _load_routings(root / "routings.csv", tenant_id, loaded)
    return loaded
