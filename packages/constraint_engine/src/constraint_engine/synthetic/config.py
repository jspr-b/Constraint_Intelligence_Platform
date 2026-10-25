"""Plant configuration for the generator (one YAML file per synthetic plant)."""

from datetime import date, time
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ShiftCfg(_Cfg):
    start: time
    end: time
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)


class BreakCfg(_Cfg):
    start: time
    minutes: int = Field(gt=0)
    covered: tuple[str, ...] = ()
    """Machines that keep running through this break."""


class ResourceCfg(_Cfg):
    code: str
    name: str
    station: str
    kind: Literal["machine", "manual"] = "machine"
    positions: tuple[int, ...] = ()
    """Staffed positions per shift, in the order of ``PlantCfg.shifts`` (empty: one)."""
    buffer_orders: int = Field(default=1000, ge=1)
    """Orders that fit in the queue in front of this machine; full queue blocks upstream."""
    downs_per_week: float = Field(default=0.0, ge=0)
    down_mean_min: float = Field(default=30.0, gt=0)
    down_reasons: tuple[str, ...] = ("MECH",)
    overtime_eur_cents_per_h: int | None = None
    extra_shift_eur_cents: int | None = None


class StepCfg(_Cfg):
    operation: str
    resource: str
    run_min_per_unit: float = Field(gt=0)
    cv: float = Field(default=0.15, ge=0)
    setup_min: float = Field(default=0.0, ge=0)
    """Applied when the machine changes setup family."""
    erp_run_min_per_unit: float | None = None
    erp_setup_min: float | None = None
    alternatives: tuple[str, ...] = ()


class ProductCfg(_Cfg):
    sku: str
    name: str
    family: str
    setup_family: str
    price_eur_cents: int = Field(ge=0)
    tvc_eur_cents: int = Field(ge=0)
    orders_per_week: float = Field(ge=0)
    qty_min: int = Field(gt=0)
    qty_max: int = Field(gt=0)
    due_days: int = Field(default=10, gt=0)
    steps: tuple[StepCfg, ...] = Field(min_length=1)


class DemandChangeCfg(_Cfg):
    from_week: int = Field(ge=1)
    """Week number counted from the first history week (1-based)."""
    sku: str
    orders_per_week: float = Field(ge=0)


class MaintenanceCfg(_Cfg):
    resource: str
    weekday: int = Field(ge=0, le=6)
    start: time
    minutes: int = Field(gt=0)


class ScrapCfg(_Cfg):
    found_at: str
    rate: float = Field(ge=0, lt=1)
    reason: str = "QUALITY"


class OutsourcingCfg(_Cfg):
    operation: str
    price_eur_cents_per_unit: int = Field(ge=0)


class OvertimeCfg(_Cfg):
    resource: str
    week: int = Field(ge=1)
    overtime_h: float = Field(ge=0)


class TeamCfg(_Cfg):
    """A team shared by several steps; together they cannot use more positions than it has."""

    code: str
    name: str
    steps: tuple[str, ...] = Field(min_length=1)
    positions: tuple[int, ...] = Field(min_length=1)
    """Team size per shift, in the order of ``PlantCfg.shifts`` (a count)."""


class ExportCfg(_Cfg):
    """What the plant shares (ADR-0009). Plants A, B and C share everything."""

    products: bool = True
    """False: no products or routings; jobs carry their value and material cost instead."""
    step_numbers: bool = True
    """False: touchpoints carry no step number; the path comes from their times."""
    forgotten_end_scan_rate: float = Field(default=0.0, ge=0, lt=1)
    """Share of finish scans at handmade steps that are forgotten (noisy bench data)."""
    order_prefix: str = "SO-"


class PlantCfg(_Cfg):
    plant_code: str
    name: str
    timezone: str = "Europe/Amsterdam"
    seed: int
    start_date: date
    """A Monday; first day of history."""
    weeks_history: int = Field(gt=0)
    weeks_orderbook: int = Field(ge=0)
    initial_backlog_weeks: float = Field(default=0.0, ge=0)
    """Orders on the floor when history starts, in weeks of demand (avoids an empty start)."""
    stations: dict[str, str]
    resources: tuple[ResourceCfg, ...]
    shifts: tuple[ShiftCfg, ...]
    breaks: tuple[BreakCfg, ...] = ()
    maintenance: tuple[MaintenanceCfg, ...] = ()
    products: tuple[ProductCfg, ...]
    demand_changes: tuple[DemandChangeCfg, ...] = ()
    scrap: tuple[ScrapCfg, ...] = ()
    outsourcing: tuple[OutsourcingCfg, ...] = ()
    overtime: tuple[OvertimeCfg, ...] = ()
    teams: tuple[TeamCfg, ...] = ()
    export: ExportCfg = ExportCfg()

    @model_validator(mode="after")
    def _references(self) -> "PlantCfg":
        if self.start_date.weekday() != 0:
            raise ValueError("start_date must be a Monday")
        codes = {r.code for r in self.resources}
        for r in self.resources:
            if r.station not in self.stations:
                raise ValueError(f"{r.code}: unknown station {r.station}")
        for p in self.products:
            for s in p.steps:
                if s.resource not in codes or not set(s.alternatives) <= codes:
                    raise ValueError(f"{p.sku}: unknown resource in step {s.operation}")
        n = len(self.shifts)
        for r in self.resources:
            if r.positions and len(r.positions) != n:
                raise ValueError(f"{r.code}: positions needs one count per shift ({n})")
        for t in self.teams:
            if not set(t.steps) <= codes or len(t.positions) != n:
                raise ValueError(f"{t.code}: unknown step, or not one size per shift ({n})")
        return self

    def resource(self, code: str) -> ResourceCfg:
        return next(r for r in self.resources if r.code == code)

    def positions(self, code: str) -> tuple[int, ...]:
        """Staffed positions per shift of a step (one per shift when not given)."""
        return self.resource(code).positions or (1,) * len(self.shifts)

    def team_of(self, code: str) -> TeamCfg | None:
        return next((t for t in self.teams if code in t.steps), None)

    def orders_per_week(self, sku: str, week: int) -> float:
        rate = next(p.orders_per_week for p in self.products if p.sku == sku)
        for change in sorted(self.demand_changes, key=lambda c: c.from_week):
            if change.sku == sku and week >= change.from_week:
                rate = change.orders_per_week
        return rate


def load_config(path: Path | str) -> PlantCfg:
    return PlantCfg.model_validate(yaml.safe_load(Path(path).read_text()))
