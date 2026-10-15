"""Store a loaded plant (standard layout) in the database, replacing that plant's data.

Runs inside the caller's tenant transaction, so row-level security applies to every write.
"""

import uuid
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Connection, Table, delete

from cip_api.db.models import Base
from constraint_engine.figure import Missing
from constraint_engine.io.plant_loader import LoadedPlant

# LoadedPlant attribute -> table. Routings are stored as their steps.
TABLES: dict[str, str] = {
    "stations": "stations",
    "resources": "resources",
    "products": "products",
    "routings": "routing_steps",
    "orders": "orders",
    "events": "operation_events",
    "calendar": "calendar_windows",
    "resource_operations": "resource_operations",
    "changeovers": "changeovers",
    "overtime": "overtime_worked",
    "capacity_costs": "capacity_costs",
    "outsourcing": "outsourcing_prices",
}


def _value(value: Any) -> Any:
    if isinstance(value, Missing):
        return None
    if isinstance(value, tuple | list):
        return ",".join(str(v) for v in value)
    return value


def _rows(plant: LoadedPlant, name: str) -> list[dict[str, Any]]:
    records: list[BaseModel] = getattr(plant, name)
    if name == "routings":
        return [
            {"sku": r.sku, **s.model_dump()}  # type: ignore[attr-defined]
            for r in records
            for s in r.steps  # type: ignore[attr-defined]
        ]
    return [r.model_dump() for r in records]


def replace_plant_data(
    conn: Connection, tenant: uuid.UUID, plant_code: str, plant: LoadedPlant
) -> dict[str, int]:
    """Replace the plant's rows for every record type the import delivered. Returns counts.

    Record types the import did not deliver (empty) are left as they are, so machines and
    stations entered on the Plant setup page survive an import without a machine list.
    """
    counts: dict[str, int] = {}
    for name, table_name in TABLES.items():
        table: Table = Base.metadata.tables[table_name]
        if not getattr(plant, name):
            continue
        conn.execute(delete(table).where(table.c.plant_code == plant_code))
        columns = [c.name for c in table.columns if not (c.primary_key and c.autoincrement is True)]
        rows = [
            {
                c: (
                    tenant
                    if c == "tenant_id"
                    else plant_code
                    if c == "plant_code"
                    else _value(record.get(c))
                )
                for c in columns
            }
            for record in _rows(plant, name)
        ]
        if rows:
            conn.execute(table.insert(), rows)
        counts[name] = len(rows)
    return counts
