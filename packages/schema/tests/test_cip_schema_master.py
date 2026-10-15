from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cip_schema.master import (
    CalendarKind,
    CalendarWindow,
    Plant,
    Product,
    Resource,
    ResourceOperation,
    Routing,
    RoutingStep,
    Station,
)

T = uuid4()


def test_plant_requires_known_timezone_and_euro() -> None:
    plant = Plant(
        tenant_id=T, plant_code="PLANT-A", name="Plant A", timezone_iana="Europe/Amsterdam"
    )
    assert plant.currency == "EUR"
    with pytest.raises(ValidationError, match="unknown IANA timezone"):
        Plant(tenant_id=T, plant_code="PLANT-A", name="Plant A", timezone_iana="Mars/Base")
    with pytest.raises(ValidationError):
        Plant(
            tenant_id=T,
            plant_code="PLANT-A",
            name="A",
            timezone_iana="UTC",
            currency="USD",  # type: ignore[arg-type]
        )


def test_station_groups_machines() -> None:
    station = Station(tenant_id=T, station_code="WELD-CELL", name="Welding cell")
    machines = [
        Resource(tenant_id=T, resource_code=c, name=c, station_code=station.station_code)
        for c in ("WLD-01", "WLD-02")
    ]
    assert {m.station_code for m in machines} == {"WELD-CELL"}
    assert all(m.parallel_units == 1 for m in machines)


def test_product_money_is_non_negative_cents() -> None:
    product = Product(
        tenant_id=T,
        sku="F-200",
        name="Frame",
        family="Frames",
        sales_price_eur_cents=98000,
        truly_variable_cost_eur_cents=43000,
    )
    assert product.sales_price_eur_cents - product.truly_variable_cost_eur_cents == 55000
    with pytest.raises(ValidationError):
        Product(
            tenant_id=T,
            sku="X",
            name="X",
            family="X",
            sales_price_eur_cents=-1,
            truly_variable_cost_eur_cents=0,
        )


def test_multi_purpose_machine_has_several_operations() -> None:
    ops = [
        ResourceOperation(tenant_id=T, resource_code="WLD-02", operation="Weld"),
        ResourceOperation(tenant_id=T, resource_code="WLD-02", operation="Grind"),
    ]
    assert {o.operation for o in ops} == {"Weld", "Grind"}


def test_routing_allows_second_visit_and_alternatives() -> None:
    routing = Routing(
        tenant_id=T,
        sku="H-12",
        steps=(
            RoutingStep(operation_seq=10, operation="Cut", resource_code="CUT-01"),
            RoutingStep(
                operation_seq=20,
                operation="Weld",
                resource_code="WLD-02",
                alternative_resource_codes=("WLD-01",),
            ),
            RoutingStep(operation_seq=30, operation="Paint", resource_code="PNT-01"),
            RoutingStep(operation_seq=40, operation="Mark", resource_code="CUT-01"),
        ),
    )
    assert routing.resources() == {"CUT-01", "WLD-01", "WLD-02", "PNT-01"}


def test_routing_rejects_duplicate_or_unordered_sequence() -> None:
    step = RoutingStep(operation_seq=10, operation="Cut", resource_code="CUT-01")
    with pytest.raises(ValidationError, match="unique"):
        Routing(tenant_id=T, sku="X", steps=(step, step))
    later = RoutingStep(operation_seq=20, operation="Weld", resource_code="WLD-01")
    with pytest.raises(ValidationError, match="ordered"):
        Routing(tenant_id=T, sku="X", steps=(later, step))


def test_alternative_cannot_be_primary() -> None:
    with pytest.raises(ValidationError, match="alternative"):
        RoutingStep(
            operation_seq=10,
            operation="Weld",
            resource_code="WLD-01",
            alternative_resource_codes=("WLD-01",),
        )


def test_calendar_window_end_after_start() -> None:
    start = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
    window = CalendarWindow(
        tenant_id=T,
        resource_code="PNT-01",
        kind=CalendarKind.BREAK,
        start_at=start,
        end_at=datetime(2026, 10, 13, 10, 30, tzinfo=UTC),
    )
    assert window.duration_min == 30
    with pytest.raises(ValidationError, match="after start_at"):
        CalendarWindow(
            tenant_id=T,
            resource_code="PNT-01",
            kind=CalendarKind.SHIFT,
            start_at=start,
            end_at=start,
        )
