"""corrections (ADR-0010): rows fixed, left out or removed in the app, next to the original

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-26 02:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from cip_api.settings import get_settings

POLICY = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corrections",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "correction_id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("plant_code", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("import_id", sa.UUID(), nullable=True),
        sa.Column("file", sa.String(length=255), nullable=True),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("column", sa.String(length=255), nullable=True),
        sa.Column("original", sa.Text(), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("target", sa.String(length=32), nullable=True),
        sa.Column("target_key", sa.Text(), nullable=True),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "correction_id"),
    )
    op.create_index(op.f("ix_corrections_tenant_id"), "corrections", ["tenant_id"], unique=False)
    op.create_index("ix_corrections_plant", "corrections", ["tenant_id", "plant_code"])
    app = get_settings().db_app_user
    op.execute("ALTER TABLE corrections ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON corrections USING ({POLICY}) WITH CHECK ({POLICY})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON corrections TO {app}")


def downgrade() -> None:
    op.drop_index("ix_corrections_plant", table_name="corrections")
    op.drop_index(op.f("ix_corrections_tenant_id"), table_name="corrections")
    op.drop_table("corrections")
