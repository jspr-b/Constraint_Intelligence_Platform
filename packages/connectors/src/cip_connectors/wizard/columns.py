"""Which column is which field of the standard model (ADR-0011 §3), from rules only.

A column is matched by what it holds first: codes found in another table's key (the steps list,
the jobs, the products), a time, a number, a few repeated words. Its name, in English, Dutch or
German, then says which of the fitting fields it is. How sure follows the same rule as a table:
content and name agree (sure), content alone (likely), name alone (unsure: asked). A column
that fits nothing is asked about, never guessed. Personal columns are never matched; they are
dropped on read and listed as such.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from cip_connectors.wizard.profile import ColumnProfile
from cip_connectors.wizard.roles import _T, STATUS_MAX, Link, Role, Sure, TableRole

Content = Literal["code", "text", "status", "int", "number", "time", "year", "week"]
Target = str | list[str] | dict[str, str]
PERSONAL = "personal (dropped on read, never shown or sent)"


@dataclass(frozen=True)
class Field:
    target: str
    content: Content
    words: tuple[str, ...] = ()
    """Name stems in English, Dutch and German. Words of 3 letters or less must be a whole word
    of the name; longer ones may be part of it (``werkplek`` in ``Werkplekcode``)."""
    not_words: tuple[str, ...] = ()
    """A name with one of these is not this field (``Aantal afkeur`` is not the good count)."""
    also: tuple[str, ...] = ()
    """When given, the name must also have one of these (scrap *and* reason)."""
    key_of: Role | None = None
    """The column holds the codes of this table's key (the steps list, the jobs ...)."""
    own_key: bool = False
    """The column is this table's own key, used by the other tables."""


SCRAP = ("scrap", "reject", "afkeur", "ausschuss", "ausschuß", "afgekeurd")
REASON = ("reason", "code", "oorzaak", "grund", "ursache", "cause")
ALT = ("alt", "alternative", "alternatief", "alternativ", "uitwijk", "ausweich")
NAME = ("name", "naam", "description", "omschrijving", "kurztext", "bezeichnung", "text")
STATION = (
    "dept",
    "department",
    "area",
    "afdeling",
    "kostenplaats",
    "kostenstelle",
    "station",
    "hall",
    "hal",
    "cell",
    "zone",
    "bereich",
    "abteilung",
)
QTY = ("qty", "quantity", "aantal", "menge", "count", "stuks", "pieces", "gereed", "good", "goed")
RESOURCE = (
    "resource",
    "werkplek",
    "machine",
    "arbeitsplatz",
    "work center",
    "workcenter",
    "workstation",
    "station",
    "step",
    "stap",
)
ORDER = ("order", "job", "auftrag", "werkbon", "bon", "productieorder", "work order", "wo")
SKU = ("item", "artikel", "material", "materiaal", "sku", "product", "part")
START = ("start", "begin", "beginn", "from", "van", "von", "ab")
END = ("end", "einde", "ende", "to", "tot", "bis", "until", "eind")
DATE_WORDS = ("datum", "date", "termin", "dag", "tag", "day")
TIME_WORDS = ("uhrzeit", "zeit", "time", "tijd", "uur")

FIELDS: dict[Role, tuple[Field, ...]] = {
    "events": (
        Field("events.resource_code", "code", RESOURCE, ALT, key_of="steps"),
        Field("events.station_code", "code", STATION, NAME),
        Field("events.order_id", "code", ORDER, key_of="orders"),
        Field(
            "events.operation_seq",
            "int",
            (
                "step no",
                "volgnr",
                "vorgang",
                "bewerkingsnr",
                "operation no",
                "seq",
                "op",
                "nr",
                "bewerking",
            ),
        ),
        Field(
            "events.event_type",
            "status",
            (
                "event",
                "action",
                "transaction",
                "meld",
                "type",
                "soort",
                "art",
                "status",
                "activity",
            ),
        ),
        Field("events.at", "time", ("time", "timestamp", "tijd", "zeit", "datum", "date", "at")),
        Field("events.quantity_units", "number", QTY, SCRAP),
        Field("events.scrap_units", "number", SCRAP, REASON),
        Field(
            "events.down_reason_code",
            "text",
            (
                "reason",
                "breakdown",
                "storing",
                "stoer",
                "stor",
                "oorzaak",
                "ursache",
                "down",
                "failure",
            ),
            SCRAP,
        ),
        Field("events.scrap_reason_code", "text", SCRAP, also=REASON),
    ),
    "hour_bookings": (
        Field("events.resource_code", "code", RESOURCE, ALT, key_of="steps"),
        Field("events.order_id", "code", ORDER, key_of="orders"),
        Field(
            "events.operation_seq",
            "int",
            ("step no", "volgnr", "vorgang", "bewerkingsnr", "operation no", "seq", "op", "nr"),
        ),
        Field("bookings.start_at", "time", ("start", "begin", "datum", "date", "tijd", "time")),
        Field(
            "bookings.duration_min",
            "number",
            ("duur", "duration", "dauer", "min", "hours", "uren", "stunden", "tijd"),
        ),
        Field("events.quantity_units", "number", QTY, SCRAP),
    ),
    "steps": (
        Field("resources.resource_code", "code", RESOURCE, own_key=True),
        Field("resources.name", "text", NAME + RESOURCE, STATION),
        Field("resources.kind", "status", ("type", "category", "soort", "art", "kind")),
        Field(
            "resources.parallel_units",
            "int",
            (
                "positions",
                "stations",
                "capacity",
                "capaciteit",
                "plaatsen",
                "plaetze",
                "places",
                "units",
                "aantal",
            ),
        ),
        Field("resources.station_code", "text", STATION),
    ),
    "calendar": (
        Field("calendar.resource_code", "code", RESOURCE, key_of="steps"),
        Field("calendar.kind", "status", ("type", "entry", "soort", "art", "kind", "category")),
        Field("calendar.start_at", "time", START, END),
        Field("calendar.end_at", "time", END),
        Field(
            "calendar.covered",
            "status",
            ("covered", "overgenomen", "uebernommen", "taken over", "cover", "vervangen"),
        ),
        Field(
            "calendar.positions",
            "int",
            (
                "slots",
                "staffed",
                "positions",
                "bezetting",
                "besetzung",
                "crew size",
                "aantal",
                "plaatsen",
            ),
        ),
    ),
    "orders": (
        Field("orders.order_id", "code", ORDER, own_key=True),
        Field("orders.sku", "code", SKU, ("cost", "kost", "datum", "date"), key_of="products"),
        Field("orders.quantity_units", "number", (*QTY, "auftragsmenge")),
        Field(
            "orders.due_at",
            "time",
            (
                "due",
                "delivery date",
                "leverdatum",
                "liefertermin",
                "liefer",
                "gevraagd",
                "requested",
                "promise",
                "termin",
            ),
            ("aflever",),
        ),
        Field("orders.status", "status", ("status",)),
        Field("orders.released_at", "time", ("release", "vrijgave", "vrijgegeven", "freigabe")),
        Field(
            "orders.shipped_at",
            "time",
            (
                "ship",
                "delivered",
                "verzonden",
                "versand",
                "aflever",
                "completed",
                "geleverd",
                "geliefert",
            ),
        ),
        Field("orders.material_ready_at", "time", ("material", "materiaal")),
        Field(
            "orders.order_value_eur_cents",
            "number",
            ("value", "waarde", "wert", "revenue", "omzet", "umsatz", "sales"),
        ),
        Field(
            "orders.material_cost_eur_cents",
            "number",
            ("material cost", "materiaalkost", "materialkost", "material"),
        ),
    ),
    "products": (
        Field("products.sku", "code", SKU, own_key=True),
        Field("products.name", "text", NAME),
        Field(
            "products.family",
            "text",
            ("group", "groep", "gruppe", "family", "familie"),
            ("colour", "color", "kleur", "lak", "farb", "paint"),
        ),
        Field(
            "products.setup_family",
            "text",
            ("colour", "color", "kleur", "lakgroep", "farb", "paint", "setup"),
        ),
        Field(
            "products.sales_price_eur_cents",
            "number",
            ("sales price", "verkoop", "verkauf", "price", "prijs", "preis"),
            ("kost", "cost", "variab"),
        ),
        Field(
            "products.truly_variable_cost_eur_cents",
            "number",
            ("variab", "kostprijs", "cost", "kosten"),
        ),
    ),
    "routings": (
        Field("routings.sku", "code", SKU, key_of="products"),
        Field(
            "routings.operation_seq",
            "int",
            ("step no", "volgnr", "vorgang", "bewerking nr", "operation no", "seq", "op", "nr"),
        ),
        Field(
            "routings.operation",
            "text",
            ("operation", "bewerking", "vorgangstext", "omschrijving", "description", "text"),
        ),
        Field("routings.resource_code", "code", RESOURCE, ALT, key_of="steps"),
        Field("routings.alternative_resource_codes", "code", ALT, key_of="steps"),
        Field("routings.standard_setup_min", "number", ("setup", "instel", "ruest", "rust")),
        Field(
            "routings.standard_run_min_per_unit",
            "number",
            (
                "run",
                "stuk",
                "per unit",
                "je stk",
                "bearbeitung",
                "bewerkingstijd",
                "cycle",
                "piece",
            ),
        ),
    ),
    "teams": (
        Field("teams.team_code", "code", ("team", "crew", "ploeg"), NAME, own_key=True),
        Field("teams.name", "text", NAME),
        Field("teams.resource_codes", "code", RESOURCE, key_of="steps"),
    ),
    "team_shifts": (
        Field("team_shifts.team_code", "code", ("team", "crew", "ploeg"), key_of="teams"),
        Field("team_shifts.start_at", "time", START, END),
        Field("team_shifts.end_at", "time", END),
        Field(
            "team_shifts.positions",
            "int",
            ("size", "staffed", "positions", "bezetting", "besetzung", "aantal"),
        ),
    ),
    "overtime": (
        Field("overtime.resource_code", "code", RESOURCE, key_of="steps"),
        Field("overtime.iso_year", "year", ("year", "jaar", "jahr")),
        Field("overtime.iso_week", "week", ("week", "kw", "wk", "woche")),
        Field("overtime.overtime_h", "number", ("hours", "uren", "stunden", "overtime", "h")),
    ),
    "capacity_costs": (
        Field("capacity_costs.resource_code", "code", RESOURCE, key_of="steps"),
        Field(
            "capacity_costs.overtime_eur_cents_per_h",
            "number",
            ("overtime", "overwerk", "ueberstunden", "rate", "per uur", "satz", "per hour"),
        ),
        Field(
            "capacity_costs.extra_shift_eur_cents",
            "number",
            ("extra", "zusatz", "shift", "dienst", "schicht", "ploeg"),
        ),
    ),
    "changeovers": (
        Field("changeovers.resource_code", "code", RESOURCE, key_of="steps"),
        Field("changeovers.from_setup_family", "text", ("from", "van", "von")),
        Field("changeovers.to_setup_family", "text", ("to", "naar", "nach")),
        Field(
            "changeovers.changeover_min",
            "number",
            ("changeover", "omstel", "ruest", "min", "tijd", "zeit", "time"),
        ),
    ),
    "outsourcing": (
        Field("outsourcing.operation", "text", ("operation", "bewerking", "vorgang")),
        Field(
            "outsourcing.price_eur_cents_per_unit",
            "number",
            ("price", "prijs", "preis", "cost", "kosten"),
        ),
    ),
}


@dataclass
class ColumnMatch:
    table: str
    column: str
    target: Target | None
    """A field (``events.at``), several (a station column that also names the station), the
    date or time part of one, or None: asked."""
    sure: Sure | None
    reasons: list[str] = field(default_factory=list)
    personal: bool = False


def _words(name: str) -> tuple[list[str], str]:
    text = unicodedata.normalize("NFKD", name.replace("ä", "ae").replace("ö", "oe"))
    text = text.replace("ü", "ue").replace("ß", "ss").replace("Ä", "Ae").replace("Ö", "Oe")
    text = "".join(c for c in text.replace("Ü", "Ue") if not unicodedata.combining(c))
    tokens = [w for w in re.split(r"[^a-z0-9]+", text.lower()) if w]
    return tokens, " ".join(tokens)


def name_hit(name: str, words: tuple[str, ...]) -> int:
    """Length of the longest word of ``words`` in the column name (0: none)."""
    tokens, joined = _words(name)
    best = 0
    for w in words:
        if len(w) <= 3:
            hit = w in tokens or f"{w}s" in tokens
        else:
            hit = w in joined or w.replace(" ", "") in "".join(tokens)
        if hit:
            best = max(best, len(w))
    return best


def _fits(c: ColumnProfile, content: Content) -> bool:
    if content == "code":
        return c.kind in ("text", "int")
    if content == "text":
        return c.kind == "text"
    if content == "status":
        return c.kind == "text" and 1 <= c.distinct <= STATUS_MAX
    if content == "int":
        return c.kind == "int"
    if content == "number":
        return c.is_number
    if content == "time":
        return c.kind in ("datetime", "date")
    if content in ("year", "week"):
        lo, hi = (2000, 2100) if content == "year" else (1, 53)
        return c.kind == "int" and bool(c.values) and all(lo <= int(v) <= hi for v in c.values)
    return False


@dataclass
class _Context:
    """What the other tables tell about this one: keys and the steps' station values."""

    roles: dict[str, Role]
    links: list[Link]
    station_values: frozenset[str] = frozenset()

    def links_to(self, table: str, column: str, role: Role) -> bool:
        return any(
            link.table == table and link.column == column and self.roles.get(link.to_table) == role
            for link in self.links
        )

    def used_by_others(self, table: str, column: str) -> bool:
        return any(link.to_table == table and link.to_column == column for link in self.links)


def _strong(t: _T, c: ColumnProfile, f: Field, ctx: _Context) -> str | None:
    """Content evidence beyond the kind of value, as a reason code."""
    if f.key_of and ctx.links_to(t.id, c.name, f.key_of):
        return f"codes_of:{f.key_of}"
    if f.own_key and c in t.key_columns() and ctx.used_by_others(t.id, c.name):
        return "key_used_by_other_tables"
    if (
        f.target.endswith("station_code")
        and ctx.station_values
        and c.values
        and c.values <= ctx.station_values
    ):
        return "values_of:steps.station"
    if f.content in ("year", "week") and _fits(c, f.content):
        return f"values_look_like:{f.content}"
    return None


def _score(t: _T, c: ColumnProfile, f: Field, ctx: _Context) -> tuple[int, str | None, int]:
    """(score, strong reason, name hit); score 0: not this field."""
    if not _fits(c, f.content):
        return 0, None, 0
    if (
        f.key_of
        and not ctx.links_to(t.id, c.name, f.key_of)
        and any(r == f.key_of for r in ctx.roles.values())
    ):
        # The table those codes belong to is in the upload, and this column's values are not
        # in it: not these codes.
        return 0, None, 0
    hit = name_hit(c.name, f.words)
    if hit and f.not_words and name_hit(c.name, f.not_words):
        hit = 0
    if hit and f.also and not name_hit(c.name, f.also):
        hit = 0
    strong = _strong(t, c, f, ctx)
    if not hit and not strong:
        return 0, None, 0
    return (20 if strong else 0) + (10 + hit if hit else 0), strong, hit


def _stem(name: str) -> str:
    tokens, _ = _words(name)
    out = "".join(tokens)
    for w in sorted(DATE_WORDS + TIME_WORDS, key=len, reverse=True):
        out = out.replace(w, "")
    return out


def match_columns(t: _T, role: Role, ctx: _Context) -> list[ColumnMatch]:
    """A match for every column of a placed table, personal columns included (never read)."""
    fields = FIELDS.get(role, ())
    cands = []
    for c in t.cols.values():
        for f in fields:
            score, strong, hit = _score(t, c, f, ctx)
            if score:
                cands.append((score, c.name, f, strong, hit))
    cands.sort(key=lambda x: -x[0])
    taken: dict[str, ColumnMatch] = {}
    used: set[str] = set()
    for _, col, f, strong, hit in cands:
        if col in taken or f.target in used:
            continue
        used.add(f.target)
        reasons = ([strong] if strong else []) + ([f"name:{col}"] if hit else [])
        sure: Sure = "sure" if hit else "likely"
        taken[col] = ColumnMatch(t.id, col, f.target, sure, reasons)
    _split_date_and_time(t, taken)
    _stations(t, role, taken)
    out = [
        taken.get(name) or ColumnMatch(t.id, name, None, None, ["not_matched"])
        for name in t.t.header
    ]
    out += [
        ColumnMatch(t.id, name, PERSONAL, "sure", ["personal"], personal=True)
        for name in t.t.personal_columns
    ]
    return out


def _split_date_and_time(t: _T, taken: dict[str, ColumnMatch]) -> None:
    """A date column and a time column that together make one moment (``Ist-Datum`` and
    ``Ist-Uhrzeit``): the time column is matched to the date column's field."""
    dated = [
        m for m in taken.values() if t.cols[m.column].kind == "date" and isinstance(m.target, str)
    ]
    times = [c for c in t.cols.values() if c.kind == "time" and c.name not in taken]
    for m in dated:
        same = [c for c in times if _stem(c.name) == _stem(m.column)]
        pick = same[0] if same else (times[0] if len(times) == 1 and len(dated) == 1 else None)
        if pick is None:
            continue
        target = str(m.target)
        m.target = {"date part of": target}
        taken[pick.name] = ColumnMatch(
            t.id, pick.name, {"time part of": target}, m.sure, [f"time_with:{m.column}"]
        )
        times.remove(pick)


def _stations(t: _T, role: Role, taken: dict[str, ColumnMatch]) -> None:
    """The steps list's station column gives each step its station and the stations
    themselves; a second station column with names gives the station names."""
    if role != "steps":
        return
    code = next((m for m in taken.values() if m.target == "resources.station_code"), None)
    if code is None:
        return
    other = [
        c
        for c in t.cols.values()
        if c.kind == "text" and c.name not in taken and name_hit(c.name, STATION)
    ]
    names = [c for c in other if name_hit(c.name, NAME)]
    if name_hit(code.column, NAME) and other:
        # The column taken first is the names; the other one holds the codes.
        names, code_col = [t.cols[code.column]], other[0]
        del taken[code.column]
        code = ColumnMatch(t.id, code_col.name, "resources.station_code", code.sure, code.reasons)
        taken[code.column] = code
    elif other and not names:
        names = other
    if names:
        code.target = ["resources.station_code", "stations.station_code"]
        taken[names[0].name] = ColumnMatch(
            t.id, names[0].name, "stations.name", "sure", [f"name:{names[0].name}"]
        )
    else:
        code.target = ["resources.station_code", "stations.name", "stations.station_code"]


def match_all(ts: list[_T], roles: list[TableRole], links: list[Link]) -> list[ColumnMatch]:
    """Column matches for every placed table; the steps list first, so its stations are known
    when the event log is matched."""
    placed = {r.table: r.role for r in roles if r.role is not None and r.sure != "unsure"}
    ctx = _Context(roles=dict(placed), links=links)
    order = sorted((t for t in ts if t.id in placed), key=lambda t: placed[t.id] != "steps")
    out: list[ColumnMatch] = []
    for t in order:
        role = placed[t.id]
        matches = match_columns(t, role, ctx)
        if role == "steps":
            for m in matches:
                if isinstance(m.target, list) and "resources.station_code" in m.target:
                    ctx.station_values = t.cols[m.column].values
        out += matches
    return out
