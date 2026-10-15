"""Row-level security: a tenant only ever sees its own rows (ADR-0004).

Runs against the docker compose database as the non-owner app role. Marked ``db``.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Double,
    Engine,
    Integer,
    String,
    Table,
    create_engine,
    text,
)
from sqlalchemy.exc import DBAPIError

from cip_api.db.models import TENANT_TABLES
from cip_api.settings import get_settings

pytestmark = pytest.mark.db
API = Path(__file__).resolve().parents[1]
A, B = uuid.UUID(int=0xA), uuid.UUID(int=0xB)


def sample_row(table: Table, tenant: uuid.UUID) -> dict[str, Any]:
    """Same natural keys for every tenant: proves two tenants may use the same codes."""
    row: dict[str, Any] = {}
    for col in table.columns:
        if col.name == "tenant_id":
            row[col.name] = tenant
        elif col.autoincrement is True and col.primary_key:
            continue
        elif isinstance(col.type, String):
            row[col.name] = "X1"
        elif isinstance(col.type, Integer | BigInteger):
            row[col.name] = 1
        elif isinstance(col.type, Double):
            row[col.name] = 1.0
        elif isinstance(col.type, Boolean):
            row[col.name] = False
        elif isinstance(col.type, DateTime):
            row[col.name] = datetime(2026, 10, 13, 7, 15, tzinfo=UTC)
    return row


def insert_sql(table: Table, row: dict[str, Any]) -> str:
    return f"INSERT INTO {table.name} ({', '.join(row)}) VALUES ({', '.join(':' + k for k in row)})"


@pytest.fixture(scope="module")
def engines() -> Iterator[tuple[Engine, Engine]]:
    settings = get_settings()
    owner = create_engine(settings.db_url(as_owner=True))
    try:
        owner.connect().close()
    except DBAPIError:
        pytest.skip("database not running: docker compose up -d db")
    cfg = Config(str(API / "alembic.ini"))
    command.upgrade(cfg, "head")
    with owner.begin() as conn:
        # Only this test's tenants: never wipe other local data (e.g. the dev tenant).
        conn.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"), {"a": A, "b": B})
        conn.execute(
            text("INSERT INTO tenants (id, name) VALUES (:a, 'Tenant A'), (:b, 'Tenant B')"),
            {"a": A, "b": B},
        )
    app = create_engine(settings.db_url())
    for tenant in (A, B):
        with app.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            for table in TENANT_TABLES:
                row = sample_row(table, tenant)
                conn.execute(text(insert_sql(table, row)), row)
    yield owner, app
    with owner.begin() as conn:
        # Only this test's tenants: never wipe other local data (e.g. the dev tenant).
        conn.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"), {"a": A, "b": B})


def test_app_role_is_not_owner_and_cannot_bypass(engines: tuple[Engine, Engine]) -> None:
    _, app = engines
    with app.connect() as conn:
        role = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        assert tuple(role) == (False, False)


@pytest.mark.parametrize("table", TENANT_TABLES, ids=lambda t: t.name)
def test_tenant_sees_only_its_own_rows(engines: tuple[Engine, Engine], table: Table) -> None:
    _, app = engines
    for tenant in (A, B):
        with app.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            tenants = (
                conn.execute(text(f"SELECT DISTINCT tenant_id FROM {table.name}")).scalars().all()
            )
            assert tenants == [tenant]


@pytest.mark.parametrize("table", TENANT_TABLES, ids=lambda t: t.name)
def test_no_tenant_set_means_no_rows(engines: tuple[Engine, Engine], table: Table) -> None:
    _, app = engines
    with app.connect() as conn:
        assert conn.execute(text(f"SELECT count(*) FROM {table.name}")).scalar_one() == 0


def test_owner_sees_both_tenants(engines: tuple[Engine, Engine]) -> None:
    owner, _ = engines
    with owner.connect() as conn:
        seen = conn.execute(
            text("SELECT count(DISTINCT tenant_id) FROM plants WHERE tenant_id IN (:a, :b)"),
            {"a": A, "b": B},
        ).scalar_one()
        assert seen == 2


def test_cannot_write_into_another_tenant(engines: tuple[Engine, Engine]) -> None:
    _, app = engines
    table = next(t for t in TENANT_TABLES if t.name == "plants")
    row = sample_row(table, B) | {"plant_code": "OTHER"}
    with pytest.raises(DBAPIError, match="row-level security"), app.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(A)})
        conn.execute(text(insert_sql(table, row)), row)
