"""A small synthetic world for auth tests: two tenants, one account per role, one station.

Everything is fake (example.test addresses, synthetic plant codes). Marked ``db`` by the tests.
"""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from cip_api.auth.pins import hash_pin
from cip_api.main import create_app
from cip_api.settings import Settings, get_settings

PERSON_ROLES = ("plant_director", "coo", "planner", "shift_lead", "it")
PIN = "4821"


@dataclass(frozen=True)
class World:
    a: uuid.UUID
    b: uuid.UUID
    owner: Engine
    station_id: uuid.UUID

    def email(self, role: str, tenant: str = "a") -> str:
        return f"{role}@{tenant}.example.test"


def make_client(
    settings: Settings | None = None, base_url: str = "http://testserver"
) -> TestClient:
    settings = settings or Settings(env="dev")
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app, base_url=base_url)


@pytest.fixture
def world() -> Iterator[World]:
    owner = create_engine(get_settings().db_url(as_owner=True))
    try:
        owner.connect().close()
    except OperationalError:
        pytest.skip("database not running: docker compose up -d db")
    a, b = uuid.uuid4(), uuid.uuid4()
    with owner.begin() as conn:
        for tenant, name in ((a, "A"), (b, "B")):
            conn.execute(
                text("INSERT INTO tenants (id, name) VALUES (:t, :n)"), {"t": tenant, "n": name}
            )
            for plant in ("PLANT-1", "PLANT-2"):
                conn.execute(
                    text(
                        "INSERT INTO plants (tenant_id, plant_code, name, timezone_iana) "
                        "VALUES (:t, :p, :p, 'Europe/Amsterdam')"
                    ),
                    {"t": tenant, "p": plant},
                )
            conn.execute(
                text(
                    "INSERT INTO resources (tenant_id, plant_code, resource_code, name, "
                    "station_code) VALUES (:t, 'PLANT-1', 'PNT-01', 'Paint line', 'ST-PNT')"
                ),
                {"t": tenant},
            )
            for role in PERSON_ROLES:
                conn.execute(
                    text(
                        "INSERT INTO users (tenant_id, email, role, plant_code, status) "
                        "VALUES (:t, :e, :r, 'PLANT-1', 'active')"
                    ),
                    {"t": tenant, "e": f"{role}@{name.lower()}.example.test", "r": role},
                )
        station_id = conn.execute(
            text(
                "INSERT INTO station_logins (tenant_id, plant_code, resource_code, pin_hash) "
                "VALUES (:t, 'PLANT-1', 'PNT-01', :h) RETURNING station_login_id"
            ),
            {"t": a, "h": hash_pin(PIN)},
        ).scalar_one()
    yield World(a, b, owner, station_id)
    with owner.begin() as conn:
        conn.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"), {"a": a, "b": b})


@pytest.fixture
def sign_in(world: World) -> Callable[..., TestClient]:
    """A dev client signed in as ``role`` (or the station) in tenant a or b."""

    def _sign_in(role: str, tenant: str = "a") -> TestClient:
        client = make_client()
        tenant_id = world.a if tenant == "a" else world.b
        if role == "station":
            body = {
                "tenant_id": str(tenant_id),
                "plant_code": "PLANT-1",
                "resource_code": "PNT-01",
                "pin": PIN,
            }
            response = client.post("/auth/station-login", json=body)
        else:
            body = {"tenant_id": str(tenant_id), "email": world.email(role, tenant)}
            response = client.post("/auth/dev-login", json=body)
        assert response.status_code == 204, response.text
        return client

    return _sign_in
