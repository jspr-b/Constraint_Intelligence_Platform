"""what the mapping wizard found in an upload, and the client's answers (CI0005 seq 02)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-26 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("imports", sa.Column("wizard", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("imports", "wizard")
