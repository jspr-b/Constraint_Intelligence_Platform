from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import TypeAdapter, ValidationError

from cip_schema.base import BaseRecord
from cip_schema.types import ResourceCode, ResourceState, StationCode, UtcDatetime

utc_adapter = TypeAdapter(UtcDatetime)
code_adapter = TypeAdapter(ResourceCode)


@given(
    st.datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2100, 1, 1),
        timezones=st.integers(-12 * 60, 14 * 60).map(lambda m: timezone(timedelta(minutes=m))),
    )
)
def test_aware_datetimes_become_utc_same_instant(value: datetime) -> None:
    result = utc_adapter.validate_python(value)
    assert result.tzinfo == UTC
    assert result == value


@given(st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1)))
def test_naive_datetimes_are_rejected(value: datetime) -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        utc_adapter.validate_python(value)


@pytest.mark.parametrize(
    "code", ["PNT-01", "WLD-02", "CUT-10", "ASMB-99", "FIN", "WELD-BENCH", "PACK", "LINE-2B"]
)
def test_valid_step_codes(code: str) -> None:
    assert code_adapter.validate_python(code) == code


@pytest.mark.parametrize(
    "code", ["pnt-01", "P", "1ST-LINE", "WELD BENCH", "WELD_1", "-FIN", "A" * 33, ""]
)
def test_invalid_step_codes(code: str) -> None:
    with pytest.raises(ValidationError):
        code_adapter.validate_python(code)


@pytest.mark.parametrize("code", ["OPERATOR-1", "BENCH-MEDEWERKER", "WORKER-3"])
def test_step_codes_never_name_a_person(code: str) -> None:
    with pytest.raises(ValidationError, match="never a person"):
        code_adapter.validate_python(code)


def test_station_code() -> None:
    assert TypeAdapter(StationCode).validate_python("WELD-CELL") == "WELD-CELL"
    with pytest.raises(ValidationError):
        TypeAdapter(StationCode).validate_python("weld cell")


def test_resource_states_match_claude_md() -> None:
    assert {s.value for s in ResourceState} == {
        "running",
        "idle",
        "starved",
        "blocked",
        "down",
        "setup",
    }


class _Example(BaseRecord):
    name: str


def test_base_record_is_frozen_and_strict_about_fields() -> None:
    record = _Example(tenant_id=uuid4(), name="x")
    with pytest.raises(ValidationError):
        record.name = "y"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="Extra inputs"):
        _Example(tenant_id=uuid4(), name="x", operator="someone")  # type: ignore[call-arg]
