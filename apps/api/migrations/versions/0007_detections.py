"""detections: the constraint found per plant, import and period, with every method's output

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-22 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from cip_api.settings import get_settings

POLICY = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "detections",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("plant_code", sa.String(length=32), nullable=False),
        sa.Column("import_id", sa.UUID(), nullable=False),
        sa.Column("period_kind", sa.String(length=8), nullable=False),
        sa.Column("period_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resource_code", sa.String(length=16), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("agreement", sa.Text(), nullable=False),
        sa.Column("reasons", sa.Text(), server_default="[]", nullable=False),
        sa.Column("methods", sa.Text(), server_default="[]", nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_detections_tenant_id"), "detections", ["tenant_id"], unique=False)
    op.create_index(
        "ix_detections_plant_period", "detections", ["tenant_id", "plant_code", "period_kind"]
    )
    app = get_settings().db_app_user
    op.execute("ALTER TABLE detections ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON detections USING ({POLICY}) WITH CHECK ({POLICY})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON detections TO {app}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE detections_id_seq TO {app}")


def downgrade() -> None:
    op.drop_index("ix_detections_plant_period", table_name="detections")
    op.drop_index(op.f("ix_detections_tenant_id"), table_name="detections")
    op.drop_table("detections")
