"""Tenant context and the provenance envelope on GET /plants/{code}/summary."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from cip_api.main import create_app
from cip_api.settings import Settings, get_settings

A, B = uuid.UUID(int=0xA1), uuid.UUID(int=0xB1)


def client_for(env: str) -> TestClient:
    app = create_app(Settings(env=env))
    app.dependency_overrides[get_settings] = lambda: Settings(env=env)
    return TestClient(app)


def test_missing_header_is_401() -> None:
    assert client_for("dev").get("/plants/P/summary").status_code == 401


def test_header_is_refused_outside_dev() -> None:
    response = client_for("production").get("/plants/P/summary", headers={"X-Tenant-Id": str(A)})
    assert response.status_code == 401
    assert response.json()["code"] == "sign_in_required"


@pytest.fixture
def seeded() -> Iterator[None]:
    owner = create_engine(get_settings().db_url(as_owner=True))
    with owner.begin() as conn:
        conn.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"), {"a": A, "b": B})
        conn.execute(
            text("INSERT INTO tenants (id, name) VALUES (:a, 'A'), (:b, 'B')"), {"a": A, "b": B}
        )
        conn.execute(
            text(
                "INSERT INTO plants (tenant_id, plant_code, name, timezone_iana) "
                "VALUES (:a, 'PLANT-A', 'Plant A', 'UTC')"
            ),
            {"a": A},
        )
        conn.execute(
            text(
                "INSERT INTO operation_events (tenant_id, plant_code, event_id, at, event_type) "
                "VALUES (:a, 'PLANT-A', 'e1', '2026-10-13T07:15:00Z', 'scan')"
            ),
            {"a": A},
        )
    yield
    with owner.begin() as conn:
        conn.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"), {"a": A, "b": B})


@pytest.mark.db
@pytest.mark.usefixtures("seeded")
def test_summary_returns_figures_for_own_tenant() -> None:
    body = client_for("dev").get("/plants/PLANT-A/summary", headers={"X-Tenant-Id": str(A)}).json()
    assert body["plant_name"] == "Plant A"
    events = body["counts"]["events"]
    assert (
        events["value"] == 1
        and events["formula_id"] == "record_count_v1"
        and events["unit"] == "rows"
    )
    assert body["event_period_start_at"].startswith("2026-10-13T07:15")


@pytest.mark.db
@pytest.mark.usefixtures("seeded")
def test_other_tenant_cannot_read_the_plant() -> None:
    response = client_for("dev").get("/plants/PLANT-A/summary", headers={"X-Tenant-Id": str(B)})
    assert response.status_code == 404
