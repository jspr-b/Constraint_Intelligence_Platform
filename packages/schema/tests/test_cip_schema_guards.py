"""Guards that keep the schema honest: exported JSON, privacy, money and time types."""

from datetime import UTC, datetime
from typing import Annotated, Any, cast

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic.fields import FieldInfo

from cip_schema.export import OUT_DIR, render
from cip_schema.registry import MODELS

DENYLIST = (
    "operator",
    "employee",
    "worker",
    "person",
    "badge",
    "first_name",
    "last_name",
    "email",
    "phone",
    "user_id",
)
MONEY_SUFFIXES = ("_eur_cents", "_eur_cents_per_h", "_eur_cents_per_unit")


def all_fields() -> list[tuple[str, str, FieldInfo]]:
    return [
        (model_name, field_name, info)
        for model_name, model in MODELS.items()
        for field_name, info in model.model_fields.items()
    ]


def adapter(info: FieldInfo) -> TypeAdapter[Any]:
    """Rebuild the field's full type (annotation plus validators) for direct validation."""
    annotation: Any = info.annotation
    if info.metadata:
        annotation = cast(Any, Annotated)[(annotation, *info.metadata)]
    return TypeAdapter(annotation)


def test_committed_json_schema_is_up_to_date() -> None:
    expected = render()
    actual = {p.name: p.read_text() for p in OUT_DIR.glob("*.schema.json")}
    assert actual == expected, "run: uv run python -m cip_schema.export"


@pytest.mark.parametrize(("model", "field", "info"), all_fields())
def test_no_person_identifying_fields(model: str, field: str, info: FieldInfo) -> None:
    hits = [word for word in DENYLIST if word in field.lower()]
    assert not hits, f"{model}.{field} looks person-identifying (ADR-0005)"


@pytest.mark.parametrize(
    ("model", "field", "info"), [f for f in all_fields() if f[1].endswith(MONEY_SUFFIXES)]
)
def test_money_fields_are_whole_cents(model: str, field: str, info: FieldInfo) -> None:
    a = adapter(info)
    assert a.validate_python(150) == 150
    with pytest.raises(ValidationError):
        a.validate_python(1.5)


@pytest.mark.parametrize(
    ("model", "field", "info"), [f for f in all_fields() if f[1].endswith("_at")]
)
def test_time_fields_are_utc(model: str, field: str, info: FieldInfo) -> None:
    a = adapter(info)
    with pytest.raises(ValidationError, match="timezone-aware"):
        a.validate_python(datetime(2026, 1, 1, 12, 0))
    assert a.validate_python(datetime(2026, 1, 1, 12, 0, tzinfo=UTC)).tzinfo == UTC


def test_every_model_is_registered() -> None:
    import cip_schema.codes
    import cip_schema.master
    import cip_schema.transactional

    defined = {
        obj.__name__
        for mod in (cip_schema.master, cip_schema.transactional, cip_schema.codes)
        for obj in vars(mod).values()
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == mod.__name__
    }
    assert defined == set(MODELS)
