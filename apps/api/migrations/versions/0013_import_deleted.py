"""import lifecycle (ADR-0010): a deleted import keeps one history line, who deleted it and when

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-26 03:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("imports", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("imports", sa.Column("deleted_by", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("imports", "deleted_by")
    op.drop_column("imports", "deleted_at")
