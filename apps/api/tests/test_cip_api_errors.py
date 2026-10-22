"""Every error is {code, message, detail}: plain English, a stable code, no internals."""

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from cip_api import errors
from cip_api.errors import CATALOG, ApiProblem


def _app() -> TestClient:
    app = FastAPI()
    errors.install(app)

    class Body(BaseModel):
        plant_code: str
        parallel_units: int

    @app.get("/problem")
    def problem() -> None:
        raise ApiProblem("plant_not_found")

    @app.get("/sized")
    def sized() -> None:
        raise ApiProblem("file_too_large", limit_mb=50)

    @app.post("/body")
    def body(b: Body) -> None:
        return None

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("psycopg.errors.UndefinedColumn: column x does not exist")

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(("code", "entry"), CATALOG.items())
def test_every_message_is_a_plain_sentence(code: str, entry: tuple[int, str]) -> None:
    status, message = entry
    assert re.fullmatch(r"[a-z_]+", code)
    assert 400 <= status < 600
    assert message[0].isupper() and message.rstrip().endswith((".", ")"))
    assert "_" not in re.sub(r"\{[a-z_]+\}", "", message), "no internal names in messages"


def test_a_problem_has_code_message_and_detail() -> None:
    response = _app().get("/problem")
    assert response.status_code == 404
    assert response.json() == {
        "code": "plant_not_found",
        "message": CATALOG["plant_not_found"][1],
        "detail": CATALOG["plant_not_found"][1],
    }
    assert "50 MB" in _app().get("/sized").json()["message"]


def test_invalid_input_names_the_fields() -> None:
    response = _app().post("/body", json={"plant_code": 1})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_input"
    assert "parallel_units" in body["message"]
    assert "loc" not in str(body) and "pydantic" not in str(body)


def test_a_crash_never_leaks_internals() -> None:
    response = _app().get("/crash")
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "server_error"
    assert "psycopg" not in response.text and "Traceback" not in response.text


def test_an_unknown_address_is_plain() -> None:
    body = _app().get("/nope").json()
    assert body["code"] == "not_found"
