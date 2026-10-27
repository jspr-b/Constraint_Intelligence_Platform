"""How the export writes dates, times and numbers (ADR-0011 §4), from the values.

Each time column gets the date-time format all its values fit. Day-month and month-day are
told apart by a day above 12 in any column written the same way; when no value tells, the
client is asked. The decimal mark comes from the number columns (``21,0`` or ``420.00``).
Durations take their unit from the column name (``Duur (min)``, ``Stunden``); when the name says
nothing the field's own unit is assumed and shown, to be checked in the summary. Times are read
in the plant's time zone (Plant setup) and stored as UTC.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from cip_connectors.wizard.codes import YES_NO_FIELDS, yes_no
from cip_connectors.wizard.columns import ColumnMatch, name_hit
from cip_connectors.wizard.roles import Sure
from cip_connectors.wizard.tables import ExportTable

SAMPLE = 400
DATES = (
    *("%d-%m-%Y", "%m-%d-%Y", "%Y-%m-%d", "%d.%m.%Y", "%m.%d.%Y", "%d/%m/%Y", "%m/%d/%Y"),
    *("%Y/%m/%d", "%d-%m-%y", "%d.%m.%y", "%d/%m/%y", "%m/%d/%y", "%Y%m%d"),
)
TIMES = ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p")
DATETIMES = tuple(f"{d}{sep}{t}" for d in DATES for sep in (" ", "T") for t in TIMES)
EXCEL = "%Y-%m-%d %H:%M"
"""Real dates in a workbook carry no format; shown as ISO."""
DEFAULT_TIMEZONE = "Europe/Amsterdam"

MINUTES = ("min", "mins", "minuten", "minutes", "minuut", "minute")
HOURS = ("h", "hr", "hrs", "uur", "uren", "hour", "hours", "stunden", "std", "stunde")


@dataclass
class TimeFormat:
    """The format of one time column (or the date or time half of one field)."""

    table: str
    column: str
    part: str | None
    """``date`` or ``time`` when the column is half of one moment."""
    format: str | None
    """None: the values do not tell day-month from month-day (asked), or fit no format."""
    options: list[str] = field(default_factory=list)
    """The formats the values fit; two when the date order is asked."""
    sure: Sure | None = None
    example: str | None = None
    """One value as written in the export, for the page to show next to its meaning."""
    real_dates: bool = False
    """Excel dates: no format needed."""
    used: bool = True
    """The column is matched to a time field. Other date columns are read too, so a column
    the client names a time later has its format ready."""


@dataclass
class Unit:
    """The unit of a duration column: as its name says, or the field's own (assumed)."""

    table: str
    column: str
    target: str
    unit: str
    """min or h."""
    field_unit: str
    sure: Sure


@dataclass
class Formats:
    times: list[TimeFormat]
    decimal: str
    decimal_sure: Sure | None
    """None: number columns use both marks (asked)."""
    delimiter: str | None
    """None when every table is a workbook sheet."""
    title_lines: int
    totals_line: bool
    byte_order_mark: bool
    units: list[Unit]
    yes_words: list[str]
    no_words: list[str]

    def datetime_shown(self) -> Any:
        """The export's date-time format as one value: one format, or a date and a time format
        when every moment is split over two columns (SAP's ``Ist-Datum`` and ``Ist-Uhrzeit``)."""
        text = [t for t in self.times if t.used and not t.real_dates and t.format]
        if not text:
            return EXCEL
        whole = Counter(t.format for t in text if t.part is None)
        if whole:
            return whole.most_common(1)[0][0]
        dates = Counter(t.format for t in text if t.part == "date")
        times = Counter(t.format for t in text if t.part == "time")
        return {
            "date": dates.most_common(1)[0][0] if dates else None,
            "time": times.most_common(1)[0][0] if times else None,
        }

    def summary(self, timezone: str) -> dict[str, Any]:
        """The shape of the test exports' ``expected.yaml`` (format section)."""
        return {
            "delimiter": {"\t": "tab"}.get(self.delimiter or "", self.delimiter),
            "decimal": self.decimal,
            "datetime": self.datetime_shown(),
            "timezone": timezone,
            "title_lines_above_header": self.title_lines,
            "totals_line_at_end": self.totals_line,
            "byte_order_mark": self.byte_order_mark,
        }


def _parses(value: str, fmt: str) -> bool:
    try:
        datetime.strptime(value, fmt)
    except ValueError:
        return False
    return True


def day_first(fmt: str) -> bool | None:
    d, m = fmt.find("%d"), fmt.find("%m")
    return None if d < 0 or m < 0 or fmt.find("%Y") == 0 else d < m


def _shape(fmt: str) -> str:
    """A format without its date order: ``%d/%m/%Y`` and ``%m/%d/%Y`` have the same shape."""
    return fmt.replace("%d", "%x").replace("%m", "%x")


def is_time_field(target: str) -> bool:
    return target.endswith(("_at", ".at"))


def _time_columns(columns: list[ColumnMatch]) -> dict[tuple[str, str], str | None]:
    """Columns matched to a time field, with ``date`` or ``time`` when they are half of one."""
    out: dict[tuple[str, str], str | None] = {}
    for m in columns:
        if m.personal:
            continue
        if isinstance(m.target, dict):
            ((key, _),) = m.target.items()
            out[(m.table, m.column)] = "date" if key.startswith("date") else "time"
        elif isinstance(m.target, str) and is_time_field(m.target):
            out[(m.table, m.column)] = None
    return out


TIMELIKE = re.compile(r"\d{1,4}[-./:]\d{1,2}")


def _time_format(t: ExportTable, column: str, part: str | None, used: bool) -> TimeFormat | None:
    """The format of a column of dates or times; None for a column of something else."""
    values = [v for r in t.rows[:SAMPLE] if (v := r.get(column)) not in (None, "")]
    if not values:
        return None
    if all(isinstance(v, datetime) for v in values):
        return TimeFormat(t.id, column, part, EXCEL, [EXCEL], "sure", None, True, used)
    text = [str(v).strip() for v in values]
    if not used and not TIMELIKE.search(text[0]):
        return None
    pool = TIMES if part == "time" else DATES if part == "date" else DATETIMES + DATES + TIMES
    options = [f for f in pool if all(_parses(v, f) for v in text)]
    if not options and not used:
        return None
    sure: Sure | None = "sure" if len(options) == 1 else None
    fmt = options[0] if len(options) == 1 else None
    return TimeFormat(t.id, column, part, fmt, options, sure, text[0], False, used)


def _settle_date_order(times: list[TimeFormat]) -> None:
    """A column whose values fit both day-month and month-day takes the order of a column
    written the same way whose values tell (a day above 12 anywhere in the export)."""
    told = {
        _shape(t.format): t.format for t in times if t.format and day_first(t.format) is not None
    }
    for t in times:
        if t.format is not None or not t.options:
            continue
        settled = {told[_shape(f)] for f in t.options if _shape(f) in told} & set(t.options)
        if len(settled) == 1:
            t.format, t.sure = settled.pop(), "sure"
        elif len({_shape(f) for f in t.options}) == 1 and len(t.options) == 2:
            t.sure = None  # day-month or month-day: asked
        else:
            # Several shapes fit (e.g. only midnight values): keep the first; it reads the same.
            t.format, t.sure = t.options[0], "likely"


DECIMAL_COMMA = re.compile(r"[-+]?(\d{1,3}(\.\d{3})+|\d+),\d+")
DECIMAL_POINT = re.compile(r"[-+]?(\d{1,3}(,\d{3})+|\d+)\.\d+")
THOUSANDS = re.compile(r"[-+]?\d{1,3}([.,]\d{3})+")


def _decimal(tables: dict[str, ExportTable], columns: list[ColumnMatch]) -> tuple[str, Sure | None]:
    comma = point = 0
    for m in columns:
        if m.personal or not isinstance(m.target, str) or m.target.endswith(("_at", "_code")):
            continue
        for r in tables[m.table].rows[:SAMPLE]:
            v = r.get(m.column)
            if not isinstance(v, str):
                continue
            v = v.strip()
            if THOUSANDS.fullmatch(v):
                continue
            comma += bool(DECIMAL_COMMA.fullmatch(v))
            point += bool(DECIMAL_POINT.fullmatch(v))
    if comma and point:
        return ("," if comma > point else "."), None
    return ("," if comma else "."), "sure" if comma or point else "likely"


def unit_of(table: str, column: str, target: str) -> Unit | None:
    """The unit of a duration column, from its name; None when the field is not a duration."""
    if "eur" in target:
        return None  # money per hour, not a duration
    field_unit = next((u for u in ("min", "h") if f"_{u}" in target), None)
    if field_unit is None:
        return None
    minutes, hours = name_hit(column, MINUTES), name_hit(column, HOURS)
    said = "min" if minutes > hours else "h" if hours else None
    return Unit(table, column, target, said or field_unit, field_unit, "sure" if said else "likely")


def _units(columns: list[ColumnMatch]) -> list[Unit]:
    out = []
    for m in columns:
        if not m.personal and isinstance(m.target, str):
            unit = unit_of(m.table, m.column, m.target)
            if unit:
                out.append(unit)
    return out


def _yes_no(
    tables: dict[str, ExportTable], columns: list[ColumnMatch]
) -> tuple[list[str], list[str]]:
    """The words a yes/no column uses (``ja``/``nee``); a word that is neither is left out and
    its rows are rejected on import with that reason."""
    yes: set[str] = set()
    no: set[str] = set()
    for m in columns:
        if m.personal or m.target not in YES_NO_FIELDS:
            continue
        for r in tables[m.table].rows:
            v = str(r.get(m.column) or "").strip()
            said = yes_no(v) if v else None
            if said is True:
                yes.add(v)
            elif said is False:
                no.add(v)
    return sorted(yes), sorted(no)


def read_formats(tables: list[ExportTable], columns: list[ColumnMatch]) -> Formats:
    by_id = {t.id: t for t in tables}
    matched = _time_columns(columns)
    times = []
    for t in tables:
        if not t.readable:
            continue
        for column in t.header:
            used = (t.id, column) in matched
            tf = _time_format(t, column, matched.get((t.id, column)), used)
            if tf is not None:
                times.append(tf)
    _settle_date_order(times)
    decimal, decimal_sure = _decimal(by_id, columns)
    text = [t for t in tables if t.readable and t.delimiter]
    delimiters = Counter(t.delimiter for t in text)
    yes, no = _yes_no(by_id, columns)
    return Formats(
        times=times,
        decimal=decimal,
        decimal_sure=decimal_sure,
        delimiter=delimiters.most_common(1)[0][0] if delimiters else None,
        title_lines=max((t.title_lines for t in tables if t.readable), default=0),
        totals_line=any(t.totals_lines for t in tables if t.readable),
        byte_order_mark=any(t.byte_order_mark for t in tables),
        units=_units(columns),
        yes_words=yes,
        no_words=no,
    )
