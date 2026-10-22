"""Getting-started progress comes from the data: plants, the latest import and its report."""

import json
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api.onboarding import _check_step
from cip_api.settings import Settings
from cip_api_testkit import World, make_client

pytestmark = pytest.mark.db
EXPORT = (
    Path(__file__).resolve().parents[3] / "data" / "synthetic" / "plant_a" / "erp_export" / "clean"
)


def _steps(body: dict[str, object]) -> dict[str, str]:
    return {s["key"]: s["state"] for s in body["steps"]}  # type: ignore[attr-defined]


@pytest.fixture
def empty_tenant(world: World) -> Iterator[TestClient]:
    """A brand-new client: one IT account, no plant."""
    tenant = uuid.uuid4()
    with world.owner.begin() as conn:
        conn.execute(text("INSERT INTO tenants (id, name) VALUES (:t, 'New')"), {"t": tenant})
        conn.execute(
            text(
                "INSERT INTO users (tenant_id, email, role, status) "
                "VALUES (:t, 'it@new.example.test', 'it', 'active')"
            ),
            {"t": tenant},
        )
    client = make_client()
    body = {"tenant_id": str(tenant), "email": "it@new.example.test"}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    yield client
    with world.owner.begin() as conn:
        conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": tenant})


def test_a_new_client_starts_by_adding_a_plant(empty_tenant: TestClient) -> None:
    body = empty_tenant.get("/onboarding").json()
    assert body["plant_code"] is None
    assert _steps(body) == {"plant": "todo", "upload": "todo", "check": "todo", "answer": "later"}
    assert body["next_step"] == "plant" and body["complete"] is False
    assert body["can_set_up"] is True
    assert body["setup_contacts"] == ["it@new.example.test"]


def test_with_a_plant_the_next_step_is_the_upload(sign_in: Callable[..., TestClient]) -> None:
    body = sign_in("it").get("/onboarding").json()
    assert body["plant_code"] == "PLANT-1"
    assert _steps(body)["plant"] == "done"
    assert body["next_step"] == "upload"


def test_after_an_import_the_available_steps_are_done(world: World, tmp_path: Path) -> None:
    client = make_client(Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True))
    body = {"tenant_id": str(world.a), "email": world.email("it")}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    files = [("files", (f.name, f.read_bytes(), "text/csv")) for f in sorted(EXPORT.glob("csv/*"))]
    created = client.post("/plants/PLANT-1/imports", files=files).json()
    uploaded = client.get("/onboarding", params={"plant_code": "PLANT-1"}).json()
    assert uploaded["steps"][1] == {
        "key": "upload",
        "state": "todo",
        "detail": "uploaded",
        "missing": [],
    }
    client.post(f"/imports/{created['import_id']}/run")
    done = client.get("/onboarding", params={"plant_code": "PLANT-1"}).json()
    assert _steps(done) == {"plant": "done", "upload": "done", "check": "done", "answer": "later"}
    assert done["complete"] is True and done["next_step"] is None


def test_roles_that_cannot_set_up_learn_who_can(sign_in: Callable[..., TestClient]) -> None:
    body = sign_in("plant_director").get("/onboarding").json()
    assert body["can_set_up"] is False
    assert body["setup_contacts"] == ["it@a.example.test"]


def _report(*statuses: str) -> SimpleNamespace:
    keys = ["orders", "routings", "products", "events", "calendar"]
    minimum = [{"key": k, "status": s} for k, s in zip(keys, statuses, strict=False)]
    return SimpleNamespace(status="done", report=json.dumps({"minimum_set": minimum}))


@pytest.mark.parametrize(
    ("statuses", "state", "detail", "items"),
    [
        (("ok",) * 5, "done", None, []),
        (("ok", "ok", "ok", "ok", "check"), "done", "confirm", ["calendar"]),
        (("ok", "partial", "ok", "missing", "check"), "todo", "missing", ["routings", "events"]),
    ],
)
def test_check_step_is_done_when_enough_is_there_and_names_what_to_confirm(
    statuses: tuple[str, ...], state: str, detail: str | None, items: list[str]
) -> None:
    step = _check_step(_report(*statuses))
    assert (step.state, step.detail, step.missing) == (state, detail, items)
