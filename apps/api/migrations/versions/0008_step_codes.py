"""step codes: a plant's own step codes, up to 32 characters (ADR-0009)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every column that holds a step (resource) code.
COLUMNS = (
    ("resources", False),
    ("routing_steps", False),
    ("resource_operations", False),
    ("calendar_windows", False),
    ("operation_events", True),
    ("changeovers", False),
    ("overtime_worked", False),
    ("capacity_costs", False),
    ("station_logins", False),
    ("sessions", True),
    ("detections", True),
)


def _alter(width_from: int, width_to: int) -> None:
    for table, nullable in COLUMNS:
        op.alter_column(
            table,
            "resource_code",
            existing_type=sa.String(length=width_from),
            type_=sa.String(length=width_to),
            existing_nullable=nullable,
        )


def upgrade() -> None:
    _alter(16, 32)


def downgrade() -> None:
    # Fails loudly if a code longer than 16 characters exists; never truncates a code.
    _alter(32, 16)
