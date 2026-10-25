"""import lifecycle (ADR-0010): every plant row knows the import it came from

NULL means the row was entered or edited in the app; those rows survive every rebuild.
Existing rows are tagged with the plant's latest finished import for the record types that
import stored; the rest stay NULL (entered on the Setup or Calendar page).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-25 22:30:00
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# LoadedPlant attribute -> table, as in cip_api.db.plant_store.TABLES at this revision.
TABLES = {
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
    "teams": "teams",
    "team_shifts": "team_shifts",
}


def upgrade() -> None:
    for table in TABLES.values():
        op.add_column(table, sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(
        "ix_operation_events_import", "operation_events", ["tenant_id", "plant_code", "import_id"]
    )
    conn = op.get_bind()
    latest = conn.execute(
        sa.text(
            "SELECT DISTINCT ON (tenant_id, plant_code) tenant_id, plant_code, import_id, report "
            "FROM imports WHERE status = 'done' ORDER BY tenant_id, plant_code, created_at DESC"
        )
    ).all()
    for row in latest:
        report = row.report if isinstance(row.report, dict) else json.loads(row.report or "{}")
        stored = report.get("stored_rows", {})
        for attr, table in TABLES.items():
            if stored.get(attr):
                conn.execute(
                    sa.text(
                        f"UPDATE {table} SET import_id = :i "
                        "WHERE tenant_id = :t AND plant_code = :p"
                    ),
                    {"i": row.import_id, "t": row.tenant_id, "p": row.plant_code},
                )


def downgrade() -> None:
    op.drop_index("ix_operation_events_import", table_name="operation_events")
    for table in TABLES.values():
        op.drop_column(table, "import_id")
