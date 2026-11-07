"""plant_flows: the plant's flow found in its touchpoints, per plant (CI0005 seq 06)

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-08 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from cip_api.settings import get_settings

POLICY = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plant_flows",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("plant_code", sa.String(length=32), nullable=False),
        sa.Column("import_id", sa.UUID(), nullable=False),
        sa.Column("flow", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "plant_code"),
    )
    op.create_index(op.f("ix_plant_flows_tenant_id"), "plant_flows", ["tenant_id"], unique=False)
    app = get_settings().db_app_user
    op.execute("ALTER TABLE plant_flows ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON plant_flows USING ({POLICY}) WITH CHECK ({POLICY})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON plant_flows TO {app}")


def downgrade() -> None:
    op.drop_index(op.f("ix_plant_flows_tenant_id"), table_name="plant_flows")
    op.drop_table("plant_flows")
