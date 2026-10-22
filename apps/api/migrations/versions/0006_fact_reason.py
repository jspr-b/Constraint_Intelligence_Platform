"""facts: down reason code (downtime by reason on the Machines page)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-22 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("facts", sa.Column("reason_code", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("facts", "reason_code")
