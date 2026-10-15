"""server-side defaults for columns with a natural default

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULTS = [
    ("plants", "currency", "'EUR'"),
    ("resources", "kind", "'machine'"),
    ("resources", "parallel_units", "1"),
    ("calendar_windows", "covered", "false"),
    ("operation_events", "quantity_units", "0"),
    ("operation_events", "scrap_units", "0"),
    ("routing_steps", "alternative_resource_codes", "''"),
]


def upgrade() -> None:
    for table, column, value in DEFAULTS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {value}")


def downgrade() -> None:
    for table, column, _ in DEFAULTS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
