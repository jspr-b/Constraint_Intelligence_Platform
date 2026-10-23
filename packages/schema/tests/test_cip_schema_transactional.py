from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cip_schema.transactional import EventType, OperationEvent, Order, OrderStatus

T = uuid4()
AT = datetime(2026, 10, 13, 7, 15, tzinfo=UTC)


def test_order_with_optional_dates() -> None:
    order = Order(tenant_id=T, order_id="SO-24187", sku="B-40", quantity_units=40, due_at=AT)
    assert order.status is OrderStatus.OPEN
    assert order.material_ready_at is None


def test_shipped_order_needs_shipped_at_after_release() -> None:
    with pytest.raises(ValidationError, match="shipped_at"):
        Order(
            tenant_id=T,
            order_id="SO-1",
            sku="B-40",
            quantity_units=1,
            due_at=AT,
            status=OrderStatus.SHIPPED,
        )
    with pytest.raises(ValidationError, match="before released_at"):
        Order(
            tenant_id=T,
            order_id="SO-1",
            sku="B-40",
            quantity_units=1,
            due_at=AT,
            released_at=AT,
            shipped_at=datetime(2026, 10, 1, tzinfo=UTC),
        )


def test_event_types_cover_all_flow_views() -> None:
    assert {e.value for e in EventType} >= {"start", "end", "move", "scan", "down_start", "scrap"}


def test_start_event_needs_a_job_and_the_step_number_is_optional() -> None:
    event = OperationEvent(
        tenant_id=T,
        event_id="e1",
        event_type=EventType.START,
        at=AT,
        resource_code="WLD-02",
        order_id="SO-24187",
        operation_seq=20,
        quantity_units=40,
    )
    assert event.resource_code == "WLD-02"
    no_number = OperationEvent(
        tenant_id=T,
        event_id="e3",
        event_type=EventType.START,
        at=AT,
        resource_code="FINISH",
        order_id="J-1",
    )
    assert no_number.operation_seq is None
    with pytest.raises(ValidationError, match="need an order_id"):
        OperationEvent(
            tenant_id=T, event_id="e2", event_type=EventType.END, at=AT, resource_code="WLD-02"
        )


def test_scan_can_be_at_station_level() -> None:
    event = OperationEvent(
        tenant_id=T,
        event_id="s1",
        event_type=EventType.SCAN,
        at=AT,
        station_code="PAINT",
        order_id="SO-24187",
    )
    assert event.resource_code is None
    with pytest.raises(ValidationError, match="station_code or resource_code"):
        OperationEvent(tenant_id=T, event_id="s2", event_type=EventType.MOVE, at=AT)


def test_down_reason_only_on_down_events() -> None:
    down = OperationEvent(
        tenant_id=T,
        event_id="d1",
        event_type=EventType.DOWN_START,
        at=AT,
        resource_code="PNT-01",
        down_reason_code="MECH",
    )
    assert down.down_reason_code == "MECH"
    with pytest.raises(ValidationError, match="down_reason_code"):
        OperationEvent(
            tenant_id=T,
            event_id="x",
            event_type=EventType.SETUP_START,
            at=AT,
            resource_code="PNT-01",
            down_reason_code="MECH",
        )


def test_scrap_needs_units() -> None:
    with pytest.raises(ValidationError, match="scrap_units"):
        OperationEvent(
            tenant_id=T,
            event_id="x",
            event_type=EventType.SCRAP,
            at=AT,
            resource_code="ASM-01",
            order_id="SO-1",
            operation_seq=40,
        )


def test_no_person_field_on_events() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        OperationEvent(
            tenant_id=T,
            event_id="x",
            event_type=EventType.DOWN_START,
            at=AT,
            resource_code="PNT-01",
            operator="someone",  # type: ignore[call-arg]
        )


def test_a_job_needs_no_product_and_can_carry_its_value() -> None:
    from cip_schema.transactional import Order

    job = Order(
        tenant_id=uuid4(),
        order_id="J-1",
        quantity_units=1,
        due_at=datetime(2026, 10, 20, tzinfo=UTC),
        order_value_eur_cents=125000,
        material_cost_eur_cents=40000,
    )
    assert job.sku is None and job.order_value_eur_cents == 125000
    with pytest.raises(ValidationError):
        Order(
            tenant_id=uuid4(),
            order_id="J-2",
            quantity_units=1,
            due_at=datetime(2026, 10, 20, tzinfo=UTC),
            order_value_eur_cents=-1,
        )
