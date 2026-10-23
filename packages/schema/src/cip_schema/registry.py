"""Every model in the standard schema, by name. Used for export and guard tests."""

from pydantic import BaseModel

from cip_schema.codes import CodeEntry
from cip_schema.master import (
    CalendarWindow,
    CapacityCost,
    Changeover,
    OutsourcingPrice,
    OvertimeWorked,
    Plant,
    Product,
    Resource,
    ResourceOperation,
    Routing,
    RoutingStep,
    Station,
    Team,
    TeamShift,
)
from cip_schema.transactional import OperationEvent, Order

MODELS: dict[str, type[BaseModel]] = {
    m.__name__: m
    for m in (
        Plant,
        Station,
        Resource,
        ResourceOperation,
        Product,
        Changeover,
        Routing,
        RoutingStep,
        CalendarWindow,
        Team,
        TeamShift,
        OvertimeWorked,
        CapacityCost,
        OutsourcingPrice,
        Order,
        OperationEvent,
        CodeEntry,
    )
}
