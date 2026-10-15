import json
import logging
import sys

import pytest
from fastapi.testclient import TestClient

from cip_api.main import create_app
from cip_api.settings import Settings


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings()))


def test_meta_lists_engine_formulas(client: TestClient) -> None:
    body = client.get("/meta").json()
    ids = {f["formula_id"] for f in body["formulas"]}
    assert {
        "throughput_per_unit_v1",
        "data_quality_score_v1",
        "oee_v1",
        "task_time_median_v1",
    } <= ids
    assert body["version"] == "0.0.0"


@pytest.mark.db
def test_health_with_services_up(client: TestClient) -> None:
    response = client.get("/health")
    assert response.json() == {"status": "ok", "db": "ok", "redis": "ok"}


def test_health_reports_unreachable_services() -> None:
    client = TestClient(create_app(Settings(db_port=1, redis_port=1)))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "db": "unreachable", "redis": "unreachable"}


def test_access_log_is_json_without_bodies(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    handler = logging.getLogger("cip").handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(sys.stdout)  # point the JSON log at this test's captured stdout
    client.get("/meta")
    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    entry = next(e for e in lines if e.get("path") == "/meta")
    assert set(entry) == {
        "at",
        "level",
        "logger",
        "event",
        "method",
        "path",
        "status",
        "duration_ms",
        "request_id",
    }
    logging.getLogger("cip").handlers.clear()
