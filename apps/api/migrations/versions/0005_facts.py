"""facts: measured numbers per plant and import, and one calculation run per import

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from cip_api.settings import get_settings

POLICY = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fact_runs",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("import_id", sa.UUID(), nullable=False),
        sa.Column("plant_code", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="calculating", nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "import_id"),
    )
    op.create_index(op.f("ix_fact_runs_tenant_id"), "fact_runs", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_fact_runs_plant_code"), "fact_runs", ["plant_code"], unique=False)

    op.create_table(
        "facts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("plant_code", sa.String(length=32), nullable=False),
        sa.Column("import_id", sa.UUID(), nullable=False),
        sa.Column("family", sa.String(length=32), nullable=False),
        sa.Column("subject_code", sa.String(length=64), nullable=False),
        sa.Column("measure", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=True),
        sa.Column("period_kind", sa.String(length=8), nullable=False),
        sa.Column("period_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("value", sa.Double(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("formula_id", sa.String(length=64), nullable=False),
        sa.Column("formula_version", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("inputs", sa.Text(), server_default="{}", nullable=False),
        sa.Column("missing", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_facts_tenant_id"), "facts", ["tenant_id"], unique=False)
    op.create_index(
        "ix_facts_plant_family", "facts", ["tenant_id", "plant_code", "family"], unique=False
    )

    app = get_settings().db_app_user
    for table in ("fact_runs", "facts"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING ({POLICY}) WITH CHECK ({POLICY})"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {app}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE facts_id_seq TO {app}")


def downgrade() -> None:
    op.drop_index("ix_facts_plant_family", table_name="facts")
    op.drop_index(op.f("ix_facts_tenant_id"), table_name="facts")
    op.drop_table("facts")
    op.drop_index(op.f("ix_fact_runs_plant_code"), table_name="fact_runs")
    op.drop_index(op.f("ix_fact_runs_tenant_id"), table_name="fact_runs")
    op.drop_table("fact_runs")
