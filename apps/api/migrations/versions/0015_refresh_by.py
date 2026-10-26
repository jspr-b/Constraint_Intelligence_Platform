"""who asked for a recalculation (CI0004 seq 07): the banner says who last changed the data

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-26 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("fact_runs", sa.Column("requested_by", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("fact_runs", "requested_by")
