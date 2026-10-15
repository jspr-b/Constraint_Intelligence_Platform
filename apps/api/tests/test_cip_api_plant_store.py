"""Loading plant_a into the database, inside a tenant, replacing earlier data."""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from cip_api.auth.sessions import tenant_conn
from cip_api.db.plant_store import TABLES, replace_plant_data
from cip_api.settings import get_settings
from constraint_engine.io.plant_loader import load_plant

pytestmark = pytest.mark.db
PLANT_A = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "plant_a"


@pytest.fixture
def tenant() -> Iterator[uuid.UUID]:
    owner = create_engine(get_settings().db_url(as_owner=True))
    t = uuid.uuid4()
    with owner.begin() as conn:
        conn.execute(text("INSERT INTO tenants (id, name) VALUES (:t, 'store test')"), {"t": t})
        conn.execute(
            text(
                "INSERT INTO plants (tenant_id, plant_code, name, timezone_iana) "
                "VALUES (:t, 'PLANT-A', 'Plant A', 'Europe/Amsterdam')"
            ),
            {"t": t},
        )
    yield t
    with owner.begin() as conn:
        conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": t})


def test_plant_a_is_stored_and_replaced(tenant: uuid.UUID) -> None:
    plant = load_plant(PLANT_A)
    settings = get_settings()
    with tenant_conn(settings, tenant) as conn:
        counts = replace_plant_data(conn, tenant, "PLANT-A", plant)
    assert counts["resources"] == 6 and counts["events"] == len(plant.events) > 1000
    assert counts["routings"] == sum(len(r.steps) for r in plant.routings)
    with tenant_conn(settings, tenant) as conn:
        again = replace_plant_data(conn, tenant, "PLANT-A", plant)
    assert again == counts
    with tenant_conn(settings, tenant) as conn:
        for name, table in TABLES.items():
            stored = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            assert stored == counts.get(name, 0), name


def test_record_types_not_in_the_import_are_kept(tenant: uuid.UUID) -> None:
    from constraint_engine.io.plant_loader import LoadedPlant

    settings = get_settings()
    full = load_plant(PLANT_A)
    with tenant_conn(settings, tenant) as conn:
        replace_plant_data(conn, tenant, "PLANT-A", full)
    events_only = LoadedPlant(plant=full.plant, events=full.events[:10])
    with tenant_conn(settings, tenant) as conn:
        counts = replace_plant_data(conn, tenant, "PLANT-A", events_only)
        machines = conn.execute(text("SELECT count(*) FROM resources")).scalar_one()
        events = conn.execute(text("SELECT count(*) FROM operation_events")).scalar_one()
    assert counts == {"events": 10} and machines == 6 and events == 10
