"""import lifecycle (ADR-0010): a changed import is a new version that keeps its place

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-25 23:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("imports", sa.Column("replaces", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("imports", sa.Column("slot_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE imports SET slot_at = created_at")


def downgrade() -> None:
    op.drop_column("imports", "slot_at")
    op.drop_column("imports", "replaces")
