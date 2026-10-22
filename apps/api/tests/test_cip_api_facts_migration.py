"""Migration 0005 (facts): upgrade and downgrade both work, and the tables are tenant-isolated.

Row isolation itself is covered for every tenant table in test_cip_api_tenancy. Marked ``db``.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from cip_api.settings import get_settings

pytestmark = pytest.mark.db
API = Path(__file__).resolve().parents[1]
TABLES = {"facts", "fact_runs", "detections"}


def test_facts_upgrade_and_downgrade() -> None:
    owner = create_engine(get_settings().db_url(as_owner=True))
    try:
        owner.connect().close()
    except DBAPIError:
        pytest.skip("database not running: docker compose up -d db")
    cfg = Config(str(API / "alembic.ini"))
    command.upgrade(cfg, "head")
    try:
        command.downgrade(cfg, "0004")
        assert not TABLES & set(inspect(owner).get_table_names())
    finally:
        command.upgrade(cfg, "head")
    assert set(inspect(owner).get_table_names()) >= TABLES
    with owner.connect() as conn:
        rls: dict[str, bool] = dict(
            conn.execute(
                text("SELECT relname, relrowsecurity FROM pg_class WHERE relname = ANY(:t)"),
                {"t": list(TABLES)},
            ).all()
        )
    assert rls == {"facts": True, "fact_runs": True, "detections": True}
    columns = {c["name"] for c in inspect(owner).get_columns("facts")}
    assert {"operation", "reason_code"} <= columns
