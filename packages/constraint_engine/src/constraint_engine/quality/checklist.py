"""Data checklist: the inputs in docs/input-data.md, checked against a loaded plant.

docs/input-data.md is the single source for what is required (Must/Should/Later) and the
minimum history; this module only decides each item's status from the data (pure).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from cip_schema.transactional import EventType
from constraint_engine.io.plant_loader import LoadedPlant

ROW = re.compile(r"^\|\s*(\d+)\s*\|")


@dataclass(frozen=True, slots=True)
class Requirement:
    number: int
    section: str
    data: str
    key_fields: str
    need: str
    min_weeks: int | None

    @property
    def level(self) -> str:
        return self.need.split(" ")[0].strip("·").strip()


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    requirement: Requirement
    status: str
    """ok, partial, missing, check (cannot be inferred from data) or n/a (not plant data)."""
    detail: str


def parse_requirements(markdown: str) -> list[Requirement]:
    out: list[Requirement] = []
    section = ""
    for line in markdown.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif ROW.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            weeks = re.search(r"≥\s*(\d+)", cells[4])
            out.append(
                Requirement(
                    int(cells[0]),
                    section,
                    cells[1],
                    cells[2],
                    cells[4],
                    int(weeks.group(1)) if weeks else None,
                )
            )
    return out


def _weeks(delta: timedelta) -> float:
    return delta.total_seconds() / (7 * 86400)


Check = Callable[[LoadedPlant, Requirement], tuple[str, str]]


def _count(name: str, label: str) -> Check:
    def check(p: LoadedPlant, _: Requirement) -> tuple[str, str]:
        n = len(getattr(p, name))
        return ("ok", f"{n} {label}") if n else ("missing", f"no {label}")

    return check


def _events(p: LoadedPlant, r: Requirement) -> tuple[str, str]:
    if not p.events:
        return "missing", "no events"
    span = _weeks(max(e.at for e in p.events) - min(e.at for e in p.events))
    ok = r.min_weeks is None or span >= r.min_weeks - 0.5
    return ("ok" if ok else "partial"), f"{span:.1f} weeks of events (minimum {r.min_weeks})"


def _orders(p: LoadedPlant, r: Requirement) -> tuple[str, str]:
    if not p.orders or not p.events:
        return (
            ("missing", "no orders")
            if not p.orders
            else ("partial", "orders but no events to date them")
        )
    now = max(e.at for e in p.events)
    back = _weeks(now - min(o.released_at or o.due_at for o in p.orders))
    ahead = _weeks(max(o.due_at for o in p.orders) - now)
    ok = r.min_weeks is None or (back >= r.min_weeks - 0.5 and ahead >= r.min_weeks - 0.5)
    return (
        "ok" if ok else "partial"
    ), f"{back:.1f} weeks back, {ahead:.1f} weeks ahead (minimum {r.min_weeks})"


def _share(numerator: int, total: int, label: str) -> tuple[str, str]:
    if total == 0:
        return "missing", f"no {label}"
    status = "ok" if numerator == total else "partial" if numerator else "missing"
    return status, f"{numerator} of {total} {label}"


def _calendar(kind: str) -> Check:
    def check(p: LoadedPlant, _: Requirement) -> tuple[str, str]:
        n = sum(1 for w in p.calendar if w.kind.value == kind)
        if n:
            return "ok", f"{n} {kind} windows"
        return ("check" if kind == "holiday" else "missing"), f"no {kind} windows listed"

    return check


def _operations(p: LoadedPlant, _: Requirement) -> tuple[str, str]:
    if not p.routings:
        return "missing", "no routings"
    steps = [s for r in p.routings for s in r.steps]
    alternatives = sum(1 for s in steps if s.alternative_resource_codes)
    machines = len({s.resource_code for s in steps})
    return "ok", f"{len(steps)} operations on {machines} machines, {alternatives} with alternatives"


def _scrap(p: LoadedPlant, _: Requirement) -> tuple[str, str]:
    found = {e.resource_code for e in p.events if e.event_type is EventType.SCRAP}
    if not found:
        return "missing", "no scrap recorded"
    return "ok", f"scrap found at {len(found)} machine(s)"


def _moves(p: LoadedPlant, _: Requirement) -> tuple[str, str]:
    n = sum(1 for e in p.events if e.event_type in (EventType.SCAN, EventType.MOVE))
    return ("ok", f"{n} move/scan events") if n else ("missing", "no move/scan events")


def _plant(p: LoadedPlant, _: Requirement) -> tuple[str, str]:
    return (
        ("missing", "plant.json missing")
        if "plant.json" in p.missing_files
        else ("ok", "plant set up")
    )


def _setup_families(p: LoadedPlant, _: Requirement) -> tuple[str, str]:
    return _share(
        sum(1 for x in p.products if x.setup_family),
        len(p.products),
        "products with a setup family",
    )


def _material(p: LoadedPlant, _: Requirement) -> tuple[str, str]:
    return _share(
        sum(1 for o in p.orders if o.material_ready_at),
        len(p.orders),
        "orders with material ready date",
    )


def _down_reasons(p: LoadedPlant, _: Requirement) -> tuple[str, str]:
    stops = [e for e in p.events if e.event_type is EventType.DOWN_START]
    return _share(sum(1 for e in stops if e.down_reason_code), len(stops), "stops with a reason")


def _code_tables(p: LoadedPlant, _: Requirement) -> tuple[str, str]:
    return "n/a", "checked during import (unknown codes are rejected rows)"


CHECKS: dict[int, Check] = {
    1: _plant,
    2: _count("stations", "stations"),
    3: _count("resources", "machines"),
    4: _operations,
    5: _count("products", "products with price and truly variable cost"),
    6: _count("routings", "routings"),
    7: _setup_families,
    8: _code_tables,
    9: _orders,
    11: _material,
    12: _events,
    13: _down_reasons,
    14: _scrap,
    15: _moves,
    16: _calendar("shift"),
    17: _calendar("break"),
    18: _calendar("maintenance"),
    19: _calendar("holiday"),
    20: _count("overtime", "machine-weeks of overtime"),
    21: _count("capacity_costs", "machines with capacity costs"),
}


def checklist(requirements: list[Requirement], plant: LoadedPlant) -> list[ChecklistItem]:
    items = []
    for r in requirements:
        if r.level == "Later":
            items.append(ChecklistItem(r, "n/a", "later"))
        elif r.number in CHECKS:
            status, detail = CHECKS[r.number](plant, r)
            items.append(ChecklistItem(r, status, detail))
        else:
            items.append(ChecklistItem(r, "n/a", "agreed or set up outside the plant data"))
    return items


def to_markdown(items: list[ChecklistItem]) -> str:
    lines = ["| # | Data | Need | Status | Detail |", "|---|---|---|---|---|"]
    for i in items:
        r = i.requirement
        lines.append(f"| {r.number} | {r.data} | {r.level} | {i.status} | {i.detail} |")
    return "\n".join(lines) + "\n"
