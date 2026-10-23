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


def test_concurrent_replaces_of_one_plant_are_serialised(tenant: uuid.UUID) -> None:
    from concurrent.futures import ThreadPoolExecutor

    plant = load_plant(PLANT_A)
    settings = get_settings()

    def store() -> dict[str, int]:
        with tenant_conn(settings, tenant) as conn:
            return replace_plant_data(conn, tenant, "PLANT-A", plant)

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: store(), range(3)))
    assert results[0] == results[1] == results[2]
    with tenant_conn(settings, tenant) as conn:
        assert conn.execute(text("SELECT count(*) FROM stations")).scalar_one() == len(
            plant.stations
        )


def test_a_workshop_with_teams_and_job_value_is_stored(tenant: uuid.UUID, tmp_path: Path) -> None:
    files = {
        "plant.json": '{"plant_code": "PLANT-A", "name": "W", "timezone_iana": "Europe/Amsterdam"}',
        "stations.csv": "station_code,name\nFINISHING,Finishing\n",
        "resources.csv": (
            "resource_code,name,station_code,kind,parallel_units\n"
            "FINISH,Finishing,FINISHING,manual,3\nPACK,Packing,FINISHING,manual,2\n"
        ),
        "orders.csv": (
            "order_id,quantity_units,due_at,status,order_value_eur_cents,material_cost_eur_cents\n"
            "J-1,4,2026-10-20T16:00:00Z,released,125000,40000\n"
        ),
        "calendar.csv": (
            "resource_code,kind,start_at,end_at,positions\n"
            "FINISH,shift,2026-10-13T04:00:00Z,2026-10-13T12:30:00Z,2\n"
        ),
        "teams.csv": "team_code,name,resource_codes\nFINISH-TEAM,Finishing,FINISH;PACK\n",
        "team_shifts.csv": (
            "team_code,start_at,end_at,positions\n"
            "FINISH-TEAM,2026-10-13T04:00:00Z,2026-10-13T12:30:00Z,3\n"
        ),
    }
    for name, content in files.items():
        (tmp_path / name).write_text(content)
    plant = load_plant(tmp_path)
    assert plant.row_errors == []
    with tenant_conn(get_settings(), tenant) as conn:
        counts = replace_plant_data(conn, tenant, "PLANT-A", plant)
        team = conn.execute(text("SELECT resource_codes FROM teams")).scalar_one()
        shift = conn.execute(text("SELECT positions FROM team_shifts")).scalar_one()
        job = conn.execute(text("SELECT sku, order_value_eur_cents FROM orders")).one()
        positions = conn.execute(text("SELECT positions FROM calendar_windows")).scalar_one()
    assert counts["teams"] == 1 and counts["team_shifts"] == 1
    assert team == "FINISH,PACK" and shift == 3 and positions == 2
    assert job.sku is None and job.order_value_eur_cents == 125000
