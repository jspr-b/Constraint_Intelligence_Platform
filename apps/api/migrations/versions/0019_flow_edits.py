"""flow_edits: the client's corrections to the flow found in the data, per plant (CI0005 seq 06)

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-08 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from cip_api.settings import get_settings

POLICY = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "flow_edits",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("plant_code", sa.String(length=32), nullable=False),
        sa.Column("edits", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_role", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "plant_code"),
    )
    op.create_index(op.f("ix_flow_edits_tenant_id"), "flow_edits", ["tenant_id"], unique=False)
    app = get_settings().db_app_user
    op.execute("ALTER TABLE flow_edits ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON flow_edits USING ({POLICY}) WITH CHECK ({POLICY})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON flow_edits TO {app}")


def downgrade() -> None:
    op.drop_index(op.f("ix_flow_edits_tenant_id"), table_name="flow_edits")
    op.drop_table("flow_edits")
