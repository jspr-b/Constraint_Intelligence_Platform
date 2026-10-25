"""Build a plant from records (e.g. database rows) instead of files (ADR-0010).

The platform keeps a plant's data in PostgreSQL and the engine reads it from there; this module
does not know about databases. The caller passes one list of plain dicts per record type, named
like the ``LoadedPlant`` attributes, and gets the same ``LoadedPlant`` the file loader gives:
same models, same validation, bad rows reported instead of raised.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError

from cip_schema.master import Plant, Routing, RoutingStep
from constraint_engine.figure import Confidence, Missing
from constraint_engine.io.plant_loader import (
    _FILES,
    _LISTS,
    OFFLINE_TENANT,
    REQUIRED,
    LoadedPlant,
    RowError,
    _reason,
)

_MODELS: dict[str, tuple[str, type[BaseModel]]] = {
    attr: (name, model) for name, (attr, model) in _FILES.items()
}


def _split(value: Any) -> tuple[str, ...]:
    """A list column: a tuple already, or text joined by ',' (database) or ';' (files)."""
    if isinstance(value, list | tuple):
        return tuple(str(v) for v in value if v)
    return tuple(v for v in str(value).replace(";", ",").split(",") if v)


def load_records(
    plant: Mapping[str, Any],
    records: Mapping[str, Sequence[Mapping[str, Any]]],
    tenant_id: UUID = OFFLINE_TENANT,
) -> LoadedPlant:
    """The plant from records. ``records["routings"]`` holds routing steps, each with its ``sku``.

    A required record type with no rows is reported in ``missing_files`` under its standard file
    name, as the file loader does for a missing file. Never raises on bad data.
    """
    loaded = LoadedPlant(plant=Missing("plant.json", "not loaded yet"))
    try:
        loaded.plant = Plant.model_validate({"tenant_id": tenant_id, **plant})
    except ValidationError as exc:
        loaded.row_errors.append(RowError("plant.json", 1, _reason(exc)))
        loaded.plant = Missing("plant.json", "invalid plant", Confidence.HIGH)

    for attr, (name, model) in _MODELS.items():
        out: list[BaseModel] = []
        for line, row in enumerate(records.get(attr, ()), start=1):
            values = {k: v for k, v in row.items() if v is not None and k != "tenant_id"}
            if (column := _LISTS.get(model)) and column in values:
                values[column] = _split(values[column])
            try:
                out.append(model.model_validate({"tenant_id": tenant_id, **values}))
            except ValidationError as exc:
                loaded.row_errors.append(RowError(name, line, _reason(exc)))
        setattr(loaded, attr, out)

    steps: dict[str, list[RoutingStep]] = defaultdict(list)
    for line, row in enumerate(records.get("routings", ()), start=1):
        values = {k: v for k, v in row.items() if v is not None and k != "tenant_id"}
        sku = values.pop("sku", None)
        values["alternative_resource_codes"] = _split(values.get("alternative_resource_codes", ""))
        try:
            if sku is None:
                raise ValueError("sku: Field required")
            steps[str(sku)].append(RoutingStep.model_validate(values))
        except (ValidationError, ValueError) as exc:
            reason = _reason(exc) if isinstance(exc, ValidationError) else str(exc)
            loaded.row_errors.append(RowError("routings.csv", line, reason))
    for sku, sku_steps in steps.items():
        try:
            loaded.routings.append(
                Routing(
                    tenant_id=tenant_id,
                    sku=sku,
                    steps=tuple(sorted(sku_steps, key=lambda s: s.operation_seq)),
                )
            )
        except ValidationError as exc:
            loaded.row_errors.append(RowError("routings.csv", 0, f"routing {sku}: {_reason(exc)}"))

    for name in REQUIRED[1:]:
        attr = _FILES[name][0]
        if not getattr(loaded, attr):
            loaded.missing_files[name] = Missing(name, "no rows in the data yet", Confidence.HIGH)
    return loaded
