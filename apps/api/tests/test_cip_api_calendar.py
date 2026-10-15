"""Capacity calendar backend: local-day timeline, covered breaks, exceptions, overtime."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api_testkit import World

pytestmark = pytest.mark.db
SignIn = Callable[..., TestClient]
SHIFT = {
    "resource_code": "PNT-01",
    "kind": "shift",
    "start_at": "2026-10-13T04:00:00Z",  # 06:00 in Amsterdam (CEST)
    "end_at": "2026-10-13T12:00:00Z",
}


def test_day_timeline_in_plant_local_time(sign_in: SignIn) -> None:
    planner = sign_in("planner")
    created = planner.post("/plants/PLANT-1/calendar/windows", json=SHIFT)
    assert created.status_code == 201, created.text
    lunch = {
        **SHIFT,
        "kind": "break",
        "start_at": "2026-10-13T09:30:00Z",
        "end_at": "2026-10-13T10:00:00Z",
    }
    planner.post("/plants/PLANT-1/calendar/windows", json=lunch)
    day = planner.get("/plants/PLANT-1/calendar", params={"day": "2026-10-13"}).json()
    assert day["timezone_iana"] == "Europe/Amsterdam"
    paint = next(m for m in day["machines"] if m["resource_code"] == "PNT-01")
    shift = next(w for w in paint["windows"] if w["kind"] == "shift")
    assert (shift["start_min"], shift["end_min"]) == (360, 840)  # 06:00-14:00 local
    assert day["data_start_at"].startswith("2026-10-13T04:00")


def test_breaks_can_be_marked_covered(world: World, sign_in: SignIn) -> None:
    planner = sign_in("planner")
    lunch = {
        **SHIFT,
        "kind": "break",
        "start_at": "2026-10-13T09:30:00Z",
        "end_at": "2026-10-13T10:00:00Z",
    }
    window = planner.post("/plants/PLANT-1/calendar/windows", json=lunch).json()
    covered = planner.patch(
        f"/plants/PLANT-1/calendar/windows/{window['id']}", json={"covered": True}
    )
    assert covered.json()["covered"] is True
    shift = planner.post("/plants/PLANT-1/calendar/windows", json=SHIFT).json()
    assert (
        planner.patch(
            f"/plants/PLANT-1/calendar/windows/{shift['id']}", json={"covered": True}
        ).status_code
        == 404
    )
    assert (
        planner.post(
            "/plants/PLANT-1/calendar/windows", json={**SHIFT, "covered": True}
        ).status_code
        == 422
    )
    with world.owner.connect() as conn:
        assert (
            "break_covered"
            in conn.execute(
                text("SELECT action FROM audit_log WHERE tenant_id = :t"), {"t": world.a}
            )
            .scalars()
            .all()
        )


def test_exceptions_and_validation(sign_in: SignIn) -> None:
    it = sign_in("it")
    maintenance = {
        **SHIFT,
        "kind": "maintenance",
        "start_at": "2026-10-31T05:00:00Z",
        "end_at": "2026-10-31T09:00:00Z",
    }
    added = it.post("/plants/PLANT-1/calendar/windows", json=maintenance).json()
    day = it.get("/plants/PLANT-1/calendar", params={"day": "2026-10-13"}).json()
    assert [e["id"] for e in day["exceptions"]] == [added["id"]]
    backwards = {**SHIFT, "end_at": "2026-10-13T03:00:00Z"}
    assert it.post("/plants/PLANT-1/calendar/windows", json=backwards).status_code == 422
    mixed = {**SHIFT, "start_at": "2026-10-13T04:00:00"}
    assert it.post("/plants/PLANT-1/calendar/windows", json=mixed).status_code == 422
    local = {**SHIFT, "start_at": "2026-10-14T06:00:00", "end_at": "2026-10-14T14:00:00"}
    stored = it.post("/plants/PLANT-1/calendar/windows", json=local).json()
    assert stored["start_at"].startswith("2026-10-14T04:00:00")  # 06:00 Amsterdam = 04:00 UTC
    unknown = {**SHIFT, "resource_code": "NOPE-1"}
    assert it.post("/plants/PLANT-1/calendar/windows", json=unknown).status_code == 422
    assert it.delete(f"/plants/PLANT-1/calendar/windows/{added['id']}").status_code == 204
    assert it.delete(f"/plants/PLANT-1/calendar/windows/{added['id']}").status_code == 404


def test_overtime_per_machine_per_week(sign_in: SignIn) -> None:
    planner = sign_in("planner")
    body = {"resource_code": "PNT-01", "iso_year": 2026, "iso_week": 42, "overtime_h": 6.5}
    assert planner.put("/plants/PLANT-1/overtime", json=body).status_code == 200
    planner.put("/plants/PLANT-1/overtime", json={**body, "overtime_h": 8})
    day = planner.get("/plants/PLANT-1/calendar", params={"day": "2026-10-13"}).json()
    assert day["overtime"] == [{**body, "overtime_h": 8.0}]


@pytest.mark.parametrize("role", ["plant_director", "coo", "shift_lead", "station"])
def test_only_planner_and_it_edit(role: str, sign_in: SignIn) -> None:
    client = sign_in(role)
    assert client.get("/plants/PLANT-1/calendar").status_code == 200
    assert client.post("/plants/PLANT-1/calendar/windows", json=SHIFT).status_code == 403
