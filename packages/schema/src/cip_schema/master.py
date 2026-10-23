"""Master data: what exists in the plant and how products flow through it.

Operations and machines are separate (ADR-0008): a machine can run several operations,
a routing may visit the same machine twice, and an operation may list alternative machines.
ERP standard times are kept for reference only; calculations use measured times.

A resource is a step (ADR-0009): a machine, a handmade bench or a check. Products and routings
are optional; capacity is positions per step per shift, or a shared team's positions.
"""

from enum import StrEnum
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cip_schema.base import BaseRecord
from cip_schema.types import EurCents, PlantCode, ResourceCode, Sku, StationCode, UtcDatetime

OperationName = str


class Plant(BaseRecord):
    plant_code: PlantCode
    name: str = Field(min_length=1)
    timezone_iana: str
    currency: Literal["EUR"] = "EUR"

    @field_validator("timezone_iana")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA timezone: {value!r}") from exc
        return value


class Station(BaseRecord):
    """A work area grouping one or more machines (e.g. a welding cell)."""

    station_code: StationCode
    name: str = Field(min_length=1)


class ResourceKind(StrEnum):
    MACHINE = "machine"
    MANUAL = "manual"
    """Handmade work at a bench or place; the client sees "handmade" (ADR-0009)."""
    STATION = "station"
    WORK_CENTRE = "work_centre"


class Resource(BaseRecord):
    """A step: a machine, a handmade bench, a check. Belongs to exactly one station.

    ``parallel_units`` is how many jobs it can work on at once (machines side by side, or
    benches); shifts may set fewer or more staffed positions (``CalendarWindow.positions``).
    """

    resource_code: ResourceCode
    name: str = Field(min_length=1)
    kind: ResourceKind = ResourceKind.MACHINE
    station_code: StationCode
    parallel_units: int = Field(default=1, ge=1)


class Product(BaseRecord):
    sku: Sku
    name: str = Field(min_length=1)
    family: str = Field(min_length=1)
    setup_family: str | None = None
    sales_price_eur_cents: EurCents = Field(ge=0)
    truly_variable_cost_eur_cents: EurCents = Field(ge=0)


class ResourceOperation(BaseRecord):
    """Capability: an operation a machine can run, with its ERP and measured rate."""

    resource_code: ResourceCode
    operation: OperationName = Field(min_length=1)
    standard_run_min_per_unit: float | None = Field(default=None, ge=0)
    measured_run_min_per_unit: float | None = Field(default=None, ge=0)


class RoutingStep(BaseModel):
    """One step of a routing. The same machine may appear in several steps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_seq: int = Field(gt=0)
    operation: OperationName = Field(min_length=1)
    resource_code: ResourceCode
    alternative_resource_codes: tuple[ResourceCode, ...] = ()
    standard_setup_min: float | None = Field(default=None, ge=0)
    standard_run_min_per_unit: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _alternatives_differ_from_primary(self) -> Self:
        if self.resource_code in self.alternative_resource_codes:
            raise ValueError("an alternative resource cannot be the primary resource")
        if len(set(self.alternative_resource_codes)) != len(self.alternative_resource_codes):
            raise ValueError("alternative resources must be unique")
        return self


class Routing(BaseRecord):
    sku: Sku
    steps: tuple[RoutingStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ascending_sequence(self) -> Self:
        seqs = [s.operation_seq for s in self.steps]
        if len(set(seqs)) != len(seqs):
            raise ValueError("operation_seq must be unique within a routing")
        if seqs != sorted(seqs):
            raise ValueError("steps must be ordered by operation_seq")
        return self

    def resources(self) -> set[str]:
        """Every machine this routing can use, primary or alternative."""
        out: set[str] = set()
        for step in self.steps:
            out.add(step.resource_code)
            out.update(step.alternative_resource_codes)
        return out


class CalendarKind(StrEnum):
    SHIFT = "shift"
    BREAK = "break"
    MAINTENANCE = "maintenance"
    HOLIDAY = "holiday"
    OVERTIME = "overtime"


class CalendarWindow(BaseRecord):
    """A period on one step's capacity calendar."""

    resource_code: ResourceCode
    kind: CalendarKind
    start_at: UtcDatetime
    end_at: UtcDatetime
    covered: bool = False
    """For breaks: the machine keeps running because someone covers the break."""
    positions: int | None = Field(default=None, ge=0)
    """For shifts: how many positions of the step are staffed (a count, never who). None means
    the step's ``parallel_units``."""

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        if self.covered and self.kind is not CalendarKind.BREAK:
            raise ValueError("only breaks can be covered")
        if self.positions is not None and self.kind is not CalendarKind.SHIFT:
            raise ValueError("only shifts have staffed positions")
        return self

    @property
    def duration_min(self) -> float:
        return (self.end_at - self.start_at).total_seconds() / 60


class Team(BaseRecord):
    """A team shared by several steps (ADR-0009): together those steps cannot have more
    positions busy than the team has on the shift. Only a count is kept, never who is in it."""

    team_code: ResourceCode
    name: str = Field(min_length=1)
    resource_codes: tuple[ResourceCode, ...] = Field(min_length=1)
    """The steps the team covers."""


class TeamShift(BaseRecord):
    """How many positions a team has during one shift (a count, never names)."""

    team_code: ResourceCode
    start_at: UtcDatetime
    end_at: UtcDatetime
    positions: int = Field(ge=0)

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class Changeover(BaseRecord):
    """Changeover time on a machine when switching from one setup family to another."""

    resource_code: ResourceCode
    from_setup_family: str = Field(min_length=1)
    to_setup_family: str = Field(min_length=1)
    changeover_min: float = Field(ge=0)


class OvertimeWorked(BaseRecord):
    """Overtime hours on one machine in one ISO week. Never per person (ADR-0005)."""

    resource_code: ResourceCode
    iso_year: int = Field(ge=2000, le=2100)
    iso_week: int = Field(ge=1, le=53)
    overtime_h: float = Field(ge=0)


class CapacityCost(BaseRecord):
    """What extra capacity on a machine costs: input for Elevate actions."""

    resource_code: ResourceCode
    overtime_eur_cents_per_h: EurCents | None = Field(default=None, ge=0)
    extra_shift_eur_cents: EurCents | None = Field(default=None, ge=0)


class OutsourcingPrice(BaseRecord):
    """Price to have an operation done outside the plant."""

    operation: OperationName = Field(min_length=1)
    sku: Sku | None = None
    price_eur_cents_per_unit: EurCents = Field(ge=0)
