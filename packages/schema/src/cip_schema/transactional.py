"""Transactional data: orders and timestamped events from the floor.

Events describe machines, stations, orders and operations. They never identify a person
(ADR-0005). Move and scan events make all four plant-flow views possible (ADR-0008).
"""

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from cip_schema.base import BaseRecord
from cip_schema.types import OrderId, ResourceCode, Sku, StationCode, UtcDatetime


class OrderStatus(StrEnum):
    OPEN = "open"
    RELEASED = "released"
    IN_PROGRESS = "in_progress"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class Order(BaseRecord):
    order_id: OrderId
    sku: Sku
    quantity_units: int = Field(gt=0)
    due_at: UtcDatetime
    status: OrderStatus = OrderStatus.OPEN
    released_at: UtcDatetime | None = None
    shipped_at: UtcDatetime | None = None
    material_ready_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def _consistent_dates(self) -> Self:
        if self.status is OrderStatus.SHIPPED and self.shipped_at is None:
            raise ValueError("a shipped order needs shipped_at")
        if self.released_at and self.shipped_at and self.shipped_at < self.released_at:
            raise ValueError("shipped_at cannot be before released_at")
        return self


class EventType(StrEnum):
    START = "start"
    END = "end"
    SETUP_START = "setup_start"
    SETUP_END = "setup_end"
    DOWN_START = "down_start"
    DOWN_END = "down_end"
    SCRAP = "scrap"
    MOVE = "move"
    SCAN = "scan"


_NEEDS_ORDER = {EventType.START, EventType.END, EventType.SCRAP}
_STATION_LEVEL = {EventType.MOVE, EventType.SCAN}
_DOWN = {EventType.DOWN_START, EventType.DOWN_END}


class OperationEvent(BaseRecord):
    """One thing that happened on the floor, at a machine or a station."""

    event_id: str = Field(min_length=1)
    event_type: EventType
    at: UtcDatetime
    resource_code: ResourceCode | None = None
    station_code: StationCode | None = None
    order_id: OrderId | None = None
    operation_seq: int | None = Field(default=None, gt=0)
    quantity_units: int = Field(default=0, ge=0)
    scrap_units: int = Field(default=0, ge=0)
    down_reason_code: str | None = None
    scrap_reason_code: str | None = None

    @model_validator(mode="after")
    def _fields_fit_event_type(self) -> Self:
        t = self.event_type
        if t in _STATION_LEVEL:
            if self.resource_code is None and self.station_code is None:
                raise ValueError(f"{t} events need a station_code or resource_code")
        elif self.resource_code is None:
            raise ValueError(f"{t} events need a resource_code")
        if t in _NEEDS_ORDER and (self.order_id is None or self.operation_seq is None):
            raise ValueError(f"{t} events need order_id and operation_seq")
        if self.down_reason_code is not None and t not in _DOWN:
            raise ValueError("down_reason_code is only allowed on down events")
        if t is EventType.SCRAP and self.scrap_units == 0:
            raise ValueError("scrap events need scrap_units > 0")
        return self
