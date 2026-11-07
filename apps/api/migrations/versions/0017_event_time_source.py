"""where an event's time comes from: scan, hour booking or estimated (CI0005 seq 05)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-27 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "operation_events",
        sa.Column("time_source", sa.String(16), nullable=False, server_default="scan"),
    )


def downgrade() -> None:
    op.drop_column("operation_events", "time_source")
