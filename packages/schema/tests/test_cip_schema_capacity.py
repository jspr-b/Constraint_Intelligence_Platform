from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cip_schema.master import (
    CalendarKind,
    CalendarWindow,
    CapacityCost,
    OutsourcingPrice,
    OvertimeWorked,
)

T = uuid4()
A = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
B = datetime(2026, 10, 13, 10, 30, tzinfo=UTC)


def test_covered_break() -> None:
    window = CalendarWindow(
        tenant_id=T,
        resource_code="PNT-01",
        kind=CalendarKind.BREAK,
        start_at=A,
        end_at=B,
        covered=True,
    )
    assert window.covered


def test_only_breaks_can_be_covered() -> None:
    with pytest.raises(ValidationError, match="only breaks"):
        CalendarWindow(
            tenant_id=T,
            resource_code="PNT-01",
            kind=CalendarKind.MAINTENANCE,
            start_at=A,
            end_at=B,
            covered=True,
        )


def test_overtime_window_kind() -> None:
    window = CalendarWindow(
        tenant_id=T, resource_code="PNT-01", kind=CalendarKind.OVERTIME, start_at=A, end_at=B
    )
    assert window.kind is CalendarKind.OVERTIME


def test_overtime_worked_per_machine_week() -> None:
    worked = OvertimeWorked(
        tenant_id=T, resource_code="WLD-01", iso_year=2026, iso_week=38, overtime_h=6.5
    )
    assert worked.overtime_h == 6.5
    with pytest.raises(ValidationError):
        OvertimeWorked(
            tenant_id=T, resource_code="WLD-01", iso_year=2026, iso_week=54, overtime_h=1
        )


def test_capacity_costs_in_cents() -> None:
    cost = CapacityCost(
        tenant_id=T,
        resource_code="PNT-01",
        overtime_eur_cents_per_h=6250,
        extra_shift_eur_cents=250000,
    )
    assert cost.overtime_eur_cents_per_h == 6250
    price = OutsourcingPrice(tenant_id=T, operation="Paint", price_eur_cents_per_unit=1800)
    assert price.sku is None
