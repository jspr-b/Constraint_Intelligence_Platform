"""What each table of an export is, and how the tables link (ADR-0011 §2-3).

Roles come from the content first: how many time columns a table has, whether one column is a
key that other tables point to, whether a column holds a few repeated words (a status). File
and sheet names only raise how sure the app is; a name alone never decides. Links are found
through shared values: the same step codes or job numbers in two tables.
"""

import re
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Literal

from cip_connectors.wizard.profile import ColumnProfile, profile
from cip_connectors.wizard.tables import ExportTable

Role = Literal[
    "events",
    "hour_bookings",
    "steps",
    "calendar",
    "orders",
    "products",
    "routings",
    "teams",
    "team_shifts",
    "overtime",
    "capacity_costs",
    "changeovers",
    "outsourcing",
]
Sure = Literal["sure", "likely", "unsure", "confirmed"]

MINIMUM: tuple[tuple[str, tuple[Role, ...]], ...] = (
    ("events", ("events", "hour_bookings")),
    ("steps", ("steps",)),
    ("calendar", ("calendar",)),
)
"""The three a diagnostic needs; hour bookings count as an event log (ADR-0011 §5)."""

TARGETS: dict[Role, tuple[str, ...]] = {
    "events": ("events",),
    "hour_bookings": ("hour_bookings",),
    "steps": ("resources", "stations"),
    "calendar": ("calendar",),
    "orders": ("orders",),
    "products": ("products",),
    "routings": ("routings",),
    "teams": ("teams",),
    "team_shifts": ("team_shifts",),
    "overtime": ("overtime",),
    "capacity_costs": ("capacity_costs",),
    "changeovers": ("changeovers",),
    "outsourcing": ("outsourcing",),
}
"""Standard tables a role fills (the steps list gives the steps and their stations)."""

NAME_HINTS: dict[Role, tuple[str, ...]] = {
    "events": ("event", "scan", "mes", "terugmeld", "rueckmeld", "transaction", "melding"),
    "hour_bookings": ("uren", "hour", "stunden", "booking", "boeking", "timesheet"),
    "steps": (
        "werkplek",
        "machine",
        "resource",
        "arbeitsplatz",
        "workstation",
        "workcenter",
        "work_center",
        "stap",
        "step",
        "station",
    ),
    "calendar": (
        "rooster",
        "schedule",
        "shift",
        "dienst",
        "kapazit",
        "capacit",
        "calendar",
        "roster",
        "planning",
        "schicht",
    ),
    "orders": ("order", "auftrag", "auftraege", "job", "werkbon", "productieorder"),
    "products": ("artikel", "item", "material", "product", "mara"),
    "routings": ("routing", "bewerking", "arbeitsplan", "operation", "plpo"),
    "teams": ("team", "crew", "ploeg"),
    "team_shifts": ("team", "crew", "ploeg"),
    "overtime": ("overuren", "overtime", "ueberstunden", "overwerk"),
    "capacity_costs": ("kosten", "cost", "tarie", "rate", "kostensaetze"),
    "changeovers": ("omstel", "changeover", "ruest", "setup"),
    "outsourcing": ("uitbeste", "subcontract", "fremd", "outsourc"),
}
DURATION_WORDS = ("duur", "duration", "dauer", "uren", "hours", "stunden", "min", "tijd")
LINK_SHARE = 0.8
"""Share of a column's values that must be found in the other table's key to call it a link."""
STATUS_MAX = 25
"""A status column holds at most this many different words."""


@dataclass
class Link:
    """``table.column`` holds values of ``to_table.to_column`` (a key)."""

    table: str
    column: str
    to_table: str
    to_column: str
    found: int
    """Distinct values of ``column`` that are in the key."""
    total: int
    """Distinct values of ``column``."""
    is_list: bool = False
    """The column lists several keys in one cell (``FINISH;PACK``)."""


@dataclass
class TableRole:
    table: str
    role: Role | None
    sure: Sure | None
    reasons: list[str] = field(default_factory=list)
    """Plain reasons, as stable codes with values, for the page to word."""


@dataclass
class _T:
    t: ExportTable
    cols: dict[str, ColumnProfile]

    @property
    def id(self) -> str:
        return self.t.id

    @property
    def name(self) -> str:
        return re.sub(r"[^a-z0-9]", "", (self.t.sheet or self.t.file.rsplit(".", 1)[0]).lower())

    def stamps(self) -> list[str]:
        """Time columns, where a date column and a time column make one timestamp."""
        dt = [c.name for c in self.cols.values() if c.kind == "datetime"]
        dates = [c.name for c in self.cols.values() if c.kind == "date"]
        times = [c.name for c in self.cols.values() if c.kind == "time"]
        return dt + (dates if len(dates) >= len(times) else times)

    def key_columns(self) -> list[ColumnProfile]:
        """Columns filled in (nearly) every row with a value no other row has."""
        rows = self.rows()
        return [
            c
            for c in self.cols.values()
            if c.kind in ("text", "int") and c.distinct == c.filled >= max(1, 0.9 * rows)
        ]

    def rows(self) -> int:
        return len(self.t.rows)


def _items(value: str) -> list[str]:
    return [x.strip() for x in re.split(r"[;,|]", value) if x.strip()]


def find_links(tables: list[_T]) -> list[Link]:
    """Every column whose values are (nearly all) the keys of another table."""
    links = []
    for child in tables:
        for col in child.cols.values():
            if col.kind not in ("text", "int") or col.distinct == 0:
                continue
            for parent in tables:
                if parent is child:
                    continue
                for key in parent.key_columns():
                    found = len(col.values & key.values)
                    if found >= min(2, col.distinct) and found >= LINK_SHARE * col.distinct:
                        links.append(
                            Link(child.id, col.name, parent.id, key.name, found, col.distinct)
                        )
                        continue
                    items = {x for v in col.values for x in _items(v)}
                    if col.kind == "text" and len(items) > col.distinct:
                        hit = len(items & key.values)
                        if hit >= 2 and hit >= LINK_SHARE * len(items):
                            links.append(
                                Link(
                                    child.id,
                                    col.name,
                                    parent.id,
                                    key.name,
                                    hit,
                                    len(items),
                                    is_list=True,
                                )
                            )
    return links


def _status_columns(t: _T, linked: set[tuple[str, str]]) -> list[str]:
    """Columns of a few repeated words: an event type, a shift kind, an order status."""
    return [
        c.name
        for c in t.cols.values()
        if c.kind == "text"
        and 2 <= c.distinct <= STATUS_MAX
        and c.filled >= 0.5 * t.rows()
        and (t.id, c.name) not in linked
    ]


def classify(tables: list[ExportTable]) -> tuple[list[TableRole], list[Link]]:
    """A role for every readable table (None when the app cannot tell) and the links."""
    ts = [_T(t, profile(t)) for t in tables if t.readable]
    links = find_links(ts)
    linked = {(link.table, link.column) for link in links}
    role: dict[str, Role] = {}
    why: dict[str, list[str]] = {t.id: [] for t in ts}

    def into(t: _T) -> set[str]:
        """Tables this table points to."""
        return {link.to_table for link in links if link.table == t.id}

    def pointed_at_by(t: _T) -> set[str]:
        return {link.table for link in links if link.to_table == t.id}

    # 1. Logs: many rows, no key column, time columns. An event log has one timestamp and a
    #    status; hour bookings have a start and a duration; a shift sheet has a start and an end.
    for t in ts:
        stamps, status = t.stamps(), _status_columns(t, linked)
        if t.key_columns() or t.rows() < 2:
            continue
        if len(stamps) == 1 and status and t.rows() >= 50:
            role[t.id] = "events"
            why[t.id] += ["one_time_column", f"status_column:{status[0]}"]
        elif len(stamps) == 1 and t.rows() >= 50 and _duration(t):
            role[t.id] = "hour_bookings"
            why[t.id] += ["start_time", f"duration_column:{_duration(t)}"]
        elif len(stamps) >= 2:
            role[t.id] = "calendar"
            why[t.id] += ["start_and_end_times"]

    logs = [t for t in ts if role.get(t.id) in ("events", "hour_bookings")]
    plans = [t for t in ts if role.get(t.id) == "calendar"]

    # 2. Lists the logs point to: the steps list (no times) and the jobs list (has dates).
    for t in ts:
        if t.id in role:
            continue
        from_logs = pointed_at_by(t) & {x.id for x in logs}
        if from_logs and t.stamps():
            role[t.id] = "orders"
            why[t.id] += ["key_used_by_the_event_log", "has_dates"]
        elif from_logs and (pointed_at_by(t) & {x.id for x in plans} or not plans):
            role[t.id] = "steps"
            why[t.id] += ["key_used_by_the_event_log"]
    steps = {t.id for t in ts if role.get(t.id) == "steps"}

    # 3. Teams list the steps they cover; a plan of teams is the team shift plan.
    for t in ts:
        if t.id not in role and any(
            link.is_list and link.table == t.id and link.to_table in steps for link in links
        ):
            role[t.id] = "teams"
            why[t.id] += ["lists_steps"]
    teams = {t.id for t in ts if role.get(t.id) == "teams"}
    for t in plans:
        if into(t) & teams and not into(t) & steps:
            role[t.id] = "team_shifts"
            why[t.id] = ["start_and_end_times", "uses_team_codes"]

    # 4. Products: a key the jobs or the routings use; routings use products and steps.
    orders = {t.id for t in ts if role.get(t.id) == "orders"}
    for t in ts:
        if t.id not in role and t.key_columns() and pointed_at_by(t) & orders and not t.stamps():
            role[t.id] = "products"
            why[t.id] += ["key_used_by_the_jobs"]
    products = {t.id for t in ts if role.get(t.id) == "products"}
    for t in ts:
        if t.id not in role and into(t) & steps and into(t) & products:
            role[t.id] = "routings"
            why[t.id] += ["uses_products_and_steps"]
    for t in ts:
        if t.id in role or t.stamps():
            continue
        others = [c for c in t.cols.values() if (t.id, c.name) not in linked]
        if into(t) & products and not into(t) & steps and t.key_columns():
            continue
        if into(t) & steps:
            if _year_and_week(others):
                role[t.id] = "overtime"
                why[t.id] += ["step_year_week"]
            elif _same_values(others) and any(c.is_number for c in others):
                role[t.id] = "changeovers"
                why[t.id] += ["step_from_to"]
            elif others and all(c.is_number or c.kind == "empty" for c in others):
                role[t.id] = "capacity_costs"
                why[t.id] += ["step_and_amounts"]

    # 5. Outsourcing: a short list of operation names from the routings, with a price.
    texts = {
        v
        for t in ts
        if role.get(t.id) == "routings"
        for c in t.cols.values()
        if c.kind == "text"
        for v in c.values
    }
    for t in ts:
        if t.id in role or t.rows() > 50 or not texts:
            continue
        names = [c for c in t.cols.values() if c.kind == "text" and c.values and c.values <= texts]
        if names and any(c.is_number for c in t.cols.values()):
            role[t.id] = "outsourcing"
            why[t.id] += ["operation_names_and_price"]

    out = []
    for t in ts:
        r = role.get(t.id)
        hint = _hint(t)
        if r is None and hint:
            out.append(TableRole(t.id, hint, "unsure", ["name_only"]))
        elif r is None:
            out.append(TableRole(t.id, None, None, ["not_placed"]))
        else:
            sure: Sure = "sure" if r in _hints(t) else "likely"
            out.append(TableRole(t.id, r, sure, why[t.id]))
    return out, links


def _duration(t: _T) -> str | None:
    for c in t.cols.values():
        name = c.name.lower()
        if c.is_number and any(w in name for w in DURATION_WORDS):
            return c.name
    return None


def _year_and_week(cols: list[ColumnProfile]) -> bool:
    ints = [c for c in cols if c.kind == "int" and c.values]

    def within(c: ColumnProfile, lo: int, hi: int) -> bool:
        return all(lo <= int(v) <= hi for v in c.values)

    return any(within(a, 2000, 2100) for a in ints) and any(within(b, 1, 53) for b in ints)


def _same_values(cols: list[ColumnProfile]) -> bool:
    """Two text columns over the same few values: a from-to table (colour to colour)."""
    texts = [c for c in cols if c.kind == "text" and c.values]
    return any(
        len(a.values & b.values) >= LINK_SHARE * min(len(a.values), len(b.values))
        for a, b in pairwise(texts)
    )


def _hints(t: _T) -> list[Role]:
    return [r for r, words in NAME_HINTS.items() if any(w in t.name for w in words)]


def _hint(t: _T) -> Role | None:
    found = _hints(t)
    return found[0] if len(found) == 1 else None
