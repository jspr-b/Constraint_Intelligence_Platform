"""automatic refresh (ADR-0010 point 10): why a calculation was asked for, and which request ran

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-26 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fact_runs",
        sa.Column("reason", sa.String(length=16), server_default="import", nullable=False),
    )
    op.add_column(
        "fact_runs",
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.add_column(
        "fact_runs", sa.Column("requested_gen", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "fact_runs", sa.Column("done_gen", sa.Integer(), server_default="0", nullable=False)
    )


def downgrade() -> None:
    for column in ("done_gen", "requested_gen", "requested_at", "reason"):
        op.drop_column("fact_runs", column)
