"""steps (ADR-0009): positions on shifts, shared teams, job value; product optional on orders

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-23 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from cip_api.settings import get_settings

POLICY = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _isolate(table: str, sequence: str | None = None) -> None:
    app = get_settings().db_app_user
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({POLICY}) WITH CHECK ({POLICY})")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {app}")
    if sequence:
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {app}")


def upgrade() -> None:
    op.add_column("calendar_windows", sa.Column("positions", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("order_value_eur_cents", sa.BigInteger(), nullable=True))
    op.add_column("orders", sa.Column("material_cost_eur_cents", sa.BigInteger(), nullable=True))
    op.alter_column("orders", "sku", existing_type=sa.String(length=64), nullable=True)
    op.create_table(
        "teams",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("plant_code", sa.String(length=32), nullable=False),
        sa.Column("team_code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("resource_codes", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "plant_code", "team_code"),
    )
    op.create_index(op.f("ix_teams_tenant_id"), "teams", ["tenant_id"], unique=False)
    _isolate("teams")
    op.create_table(
        "team_shifts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("plant_code", sa.String(length=32), nullable=False),
        sa.Column("team_code", sa.String(length=32), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("positions", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_team_shifts_tenant_id"), "team_shifts", ["tenant_id"], unique=False)
    _isolate("team_shifts", "team_shifts_id_seq")


def downgrade() -> None:
    op.drop_index(op.f("ix_team_shifts_tenant_id"), table_name="team_shifts")
    op.drop_table("team_shifts")
    op.drop_index(op.f("ix_teams_tenant_id"), table_name="teams")
    op.drop_table("teams")
    # Fails loudly if a job without a product exists; never invents one.
    op.alter_column("orders", "sku", existing_type=sa.String(length=64), nullable=False)
    op.drop_column("orders", "material_cost_eur_cents")
    op.drop_column("orders", "order_value_eur_cents")
    op.drop_column("calendar_windows", "positions")
