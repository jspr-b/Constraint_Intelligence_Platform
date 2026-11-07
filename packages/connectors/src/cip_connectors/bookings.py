"""Hour bookings become touchpoints (ADR-0011 §5, CI0005 seq 05).

Many plants only book hours per job and step. A booking with a start and a duration becomes a
start and an end event at the booked times (``time_source=booking``). A booking with a date
and hours only becomes the same two events placed in that day's shift on its step, one after
the other in the order of the file (``time_source=estimated``): the times are the app's
placing, never measured, and are said to be so. With no shift for that step on that day the
booking cannot be placed and is rejected with that reason; nothing is invented.

Bookings tell how long a job was worked at a step. They do not tell waiting, blocking, setups
or stops, so the engine trusts them less (see ``constraint_engine.detection``).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

BOOKING_COLUMNS = (
    "order_id",
    "operation_seq",
    "resource_code",
    "start_at",
    "duration_min",
    "quantity_units",
    "scrap_units",
)
"""What a booking row is mapped to before it becomes events."""
BOOKING_REQUIRED = ("order_id", "resource_code", "start_at", "duration_min")

_EVENT_FIELDS = ("resource_code", "order_id", "operation_seq")


@dataclass(frozen=True)
class Booking:
    line: int
    record: dict[str, str]
    """The mapped row: ``BOOKING_COLUMNS`` with ``start_at`` in UTC (standard layout)."""


@dataclass(frozen=True)
class Unplaced:
    line: int
    code: str
    reason: str
    value: str
    field: str
    """The booking field the reason is about: ``start_at`` or ``duration_min``."""


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def _text(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _minutes(text: str) -> Decimal | None:
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


def _pair(
    record: dict[str, str], start: datetime, minutes: Decimal, source: str
) -> list[dict[str, str]]:
    base = {k: record[k] for k in _EVENT_FIELDS if record.get(k)}
    end = start + timedelta(minutes=float(minutes))
    return [
        {**base, "event_type": "start", "at": _text(start), "time_source": source},
        {
            **base,
            "event_type": "end",
            "at": _text(end),
            "quantity_units": record.get("quantity_units") or "0",
            "scrap_units": record.get("scrap_units") or "0",
            "time_source": source,
        },
    ]


def _shifts(calendar: list[dict[str, str]]) -> dict[str, list[tuple[datetime, datetime]]]:
    """Shift windows per step, in time order."""
    out: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    for row in calendar:
        if row.get("kind") == "shift" and row.get("start_at") and row.get("end_at"):
            out[row["resource_code"]].append((_at(row["start_at"]), _at(row["end_at"])))
    for windows in out.values():
        windows.sort()
    return out


def booking_events(
    bookings: list[Booking],
    has_time: bool,
    calendar: list[dict[str, str]],
    timezone: str,
) -> tuple[list[dict[str, str]], list[Unplaced]]:
    """Start and end events for each booking, without event ids (the importer adds them).

    ``has_time``: the bookings have a start time. Without one, ``start_at`` is the day the
    hours were booked (plant time), and the booking is placed in that day's first shift on its
    step, after the bookings before it in the file.
    """
    events: list[dict[str, str]] = []
    unplaced: list[Unplaced] = []
    zone = ZoneInfo(timezone)
    shifts = _shifts(calendar) if not has_time else {}
    placed_until: dict[tuple[str, object], datetime] = {}
    for b in bookings:
        minutes = _minutes(b.record["duration_min"])
        if minutes is None:
            unplaced.append(
                Unplaced(
                    b.line,
                    "not_a_duration",
                    "not a duration",
                    b.record["duration_min"],
                    "duration_min",
                )
            )
            continue
        start = _at(b.record["start_at"])
        if has_time:
            events += _pair(b.record, start, minutes, "booking")
            continue
        step, day = b.record["resource_code"], start.astimezone(zone).date()
        windows = [w for w in shifts.get(step, []) if w[0].astimezone(zone).date() == day]
        if not windows:
            unplaced.append(
                Unplaced(
                    b.line,
                    "no_shift_for_booking",
                    f"no shift on {step} on {day.isoformat()} to place the booked hours in",
                    day.isoformat(),
                    "start_at",
                )
            )
            continue
        begin = placed_until.get((step, day), windows[0][0])
        events += _pair(b.record, begin, minutes, "estimated")
        placed_until[(step, day)] = begin + timedelta(minutes=float(minutes))
    return events, unplaced
