"""What the plant's own codes mean (ADR-0011 §4), from rules only.

A status column (an event type, an order status, a shift kind, a step kind) holds a few
repeated words. Each word gets a meaning from known words in English, Dutch and German, the
short status codes of common ERPs (SAP's ``FREI``), or a start/end pair (``OMSTEL_START``,
``RUEST_A``). How sure: a known word or a pair of known words (sure); one known word inside a
longer code, a shortened word or a one-letter pair (likely: the client checks); nothing (asked).
A code is never dropped: until it has a meaning it is a question.

Steps and stations keep the plant's own codes; nothing is invented for them (ADR-0011 §4).
"""

from collections import Counter
from dataclasses import dataclass, field

from cip_connectors.wizard.columns import ColumnMatch, _words
from cip_connectors.wizard.profile import norm
from cip_connectors.wizard.roles import STATUS_MAX, Sure
from cip_connectors.wizard.tables import ExportTable

WORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "events.event_type": {
        "start": ("start", "started", "gestart", "begin", "begonnen", "beginn", "clock on", "go"),
        "end": (
            *("end", "ende", "einde", "eind", "finished", "finish", "gereed", "klaar", "done"),
            *("completed", "complete", "clock off", "fertig", "beendet"),
        ),
        "scrap": ("scrap", "scrapped", "rejected", "reject", "afkeur", "afgekeurd", "ausschuss"),
        "scan": ("arrived", "arrive", "arrival", "aankomst", "received", "ankunft", "binnen"),
        "move": ("departed", "depart", "departure", "vertrek", "dispatched", "leave", "abgang"),
        "down_start": ("breakdown", "stop", "stopped", "interrupted", "failure", "stoerung"),
        "down_end": ("repaired", "resumed", "restart", "restarted", "hersteld", "behoben"),
    },
    "orders.status": {
        "open": ("open", "offen", "new", "nieuw", "created", "aangemaakt", "eroeffnet", "eroef"),
        "released": ("released", "release", "vrijgegeven", "freigegeben", "frei"),
        "in_progress": (
            *("in progress", "in process", "in bewerking", "in arbeit", "in productie", "wip"),
            *("teilrueckgemeldet", "trueck"),
        ),
        "shipped": (
            *("shipped", "delivered", "verzonden", "geleverd", "geliefert", "versandt"),
            "glft",
        ),
        "cancelled": ("cancelled", "canceled", "geannuleerd", "storniert", "vervallen"),
    },
    "calendar.kind": {
        "shift": ("shift", "dienst", "schicht", "ploeg"),
        "break": ("break", "pause", "pauze", "lunch", "rust"),
        "maintenance": ("maintenance", "onderhoud", "wartung", "instandhaltung", "service"),
        "holiday": ("holiday", "public holiday", "feestdag", "feiertag", "closed", "gesloten"),
        "overtime": ("overtime", "overwerk", "ueberstunden"),
    },
    "resources.kind": {
        "machine": ("machine", "equipment", "maschine", "automatic", "automaat", "cnc"),
        "manual": (
            *("manual", "handwork", "handwerk", "handmatig", "hand", "handarbeit", "manuell"),
            *("bench", "werkbank", "handmade"),
        ),
    },
}
"""Known words per meaning, written as ``_words`` gives them (lower case, umlauts as ae/oe/ue).
SAP system statuses (``ERÖF``, ``FREI``, ``TRÜCK``, ``GLFT``) are known codes, not guesses."""

ACTIVITY = {
    "setup": ("setup", "set up", "omstel", "omstellen", "ruest", "rust", "changeover", "instel"),
    "down": ("down", "storing", "stoer", "stoerung", "breakdown", "failure", "stop"),
}
PHASE = {
    "start": ("start", "begin", "beginn", "anfang", "aanvang", "on"),
    "end": ("end", "einde", "ende", "eind", "off"),
}
LETTER = {"a": "start", "b": "start", "e": "end"}
"""One-letter phase in a pair: SAP's ``RUEST_A`` (Anfang) and ``RUEST_E`` (Ende)."""

MEANINGS: dict[str, tuple[str, ...]] = {
    "events.event_type": (
        *("start", "end", "setup_start", "setup_end", "down_start", "down_end"),
        *("scrap", "scan", "move"),
    ),
    "orders.status": ("open", "released", "in_progress", "shipped", "cancelled"),
    "calendar.kind": ("shift", "break", "maintenance", "holiday", "overtime"),
    "resources.kind": ("machine", "manual"),
}
"""Every meaning a code of each status field can have, as in ``cip_schema``: the client's
choices and the only answers the AI may give."""
CODE_FIELDS = tuple(MEANINGS)
YES = ("yes", "ja", "j", "y", "true", "waar", "wahr", "x", "1")
NO = ("no", "nee", "nein", "n", "false", "onwaar", "falsch", "0")
YES_NO_FIELDS = ("calendar.covered",)


@dataclass
class CodeMatch:
    """One code of a status column and what it means."""

    target: str
    """The status field (``events.event_type``)."""
    table: str
    column: str
    code: str
    meaning: str | None
    sure: Sure | None
    reasons: list[str] = field(default_factory=list)
    rows: int = 0


@dataclass
class StepFound:
    """A step of the steps list, with the plant's own code (never one the app made up)."""

    code: str
    name: str | None
    station: str | None
    kind: str | None
    """machine or manual when the steps list says so; None: not said."""


def meaning_of(field_name: str, code: str) -> tuple[str | None, Sure | None, str]:
    """(meaning, how sure, reason code) for one code of a status field."""
    words = WORDS[field_name]
    tokens, joined = _words(code)
    exact = [m for m, ws in words.items() if joined in ws]
    if len(exact) == 1:
        return exact[0], "sure", "known_word"
    if field_name == "events.event_type":
        pair = _pair(tokens, joined)
        if pair:
            return pair
    inside = {m for m, ws in words.items() for w in ws if w in tokens or f" {w} " in f" {joined} "}
    if len(inside) == 1:
        return inside.pop(), "likely", "word_in_code"
    short = {
        m
        for m, ws in words.items()
        for w in ws
        if len(joined) >= 3 and w.startswith(joined.replace(" ", ""))
    }
    if len(short) == 1:
        return short.pop(), "likely", "shortened_word"
    return None, None, "not_known"


def _pair(tokens: list[str], joined: str) -> tuple[str, Sure, str] | None:
    """An activity and a phase: ``SETUP BEGIN``, ``STORING_EINDE``, ``RUEST_A``."""
    activity = [a for a, ws in ACTIVITY.items() if any(w in tokens or w in joined for w in ws)]
    if len(activity) != 1 or len(tokens) < 2:
        return None
    rest = tokens[-1]
    phase = [p for p, ws in PHASE.items() if rest in ws]
    if len(phase) == 1:
        return f"{activity[0]}_{phase[0]}", "sure", "start_end_pair"
    if rest in LETTER:
        return f"{activity[0]}_{LETTER[rest]}", "likely", "start_end_letter"
    return None


def yes_no(code: str) -> bool | None:
    _, joined = _words(code)
    return True if joined in YES else False if joined in NO else None


def match_codes(tables: list[ExportTable], columns: list[ColumnMatch]) -> list[CodeMatch]:
    """A meaning for every code in every status column the columns were matched to."""
    by_id = {t.id: t for t in tables}
    out: list[CodeMatch] = []
    for m in columns:
        if m.personal or not isinstance(m.target, str) or m.target not in CODE_FIELDS:
            continue
        counts = Counter(norm(r.get(m.column)) for r in by_id[m.table].rows)
        counts.pop("", None)
        for code, rows in sorted(counts.items()):
            meaning, sure, reason = meaning_of(m.target, code)
            out.append(CodeMatch(m.target, m.table, m.column, code, meaning, sure, [reason], rows))
    return out


def steps_found(tables: list[ExportTable], columns: list[ColumnMatch]) -> list[StepFound]:
    """Every step of the steps list, with its name, station and kind as the export says."""
    by_id = {t.id: t for t in tables}

    def col(table: str, f: str) -> str | None:
        return next(
            (
                m.column
                for m in columns
                if m.table == table
                and (m.target == f or (isinstance(m.target, list) and f in m.target))
            ),
            None,
        )

    out: list[StepFound] = []
    for table in dict.fromkeys(m.table for m in columns if m.target == "resources.resource_code"):
        code_col = col(table, "resources.resource_code")
        name_col, station_col = col(table, "resources.name"), col(table, "resources.station_code")
        kind_col = col(table, "resources.kind")
        for r in by_id[table].rows:
            code = norm(r.get(code_col)) if code_col else ""
            if not code or any(s.code == code for s in out):
                continue
            kind = meaning_of("resources.kind", norm(r.get(kind_col)))[0] if kind_col else None
            out.append(
                StepFound(
                    code=code,
                    name=norm(r.get(name_col)) or None if name_col else None,
                    station=norm(r.get(station_col)) or None if station_col else None,
                    kind=kind,
                )
            )
    return out


def code_values(tables: list[ExportTable]) -> dict[tuple[str, str], dict[str, int]]:
    """Rows per value of every column of a few repeated words, so a column the client names a
    status field later has its codes ready."""
    out: dict[tuple[str, str], dict[str, int]] = {}
    for t in tables:
        if not t.readable:
            continue
        for column in t.header:
            counts = Counter(norm(r.get(column)) for r in t.rows)
            counts.pop("", None)
            if 1 <= len(counts) <= STATUS_MAX and not all(c.isdigit() for c in counts):
                out[(t.id, column)] = dict(sorted(counts.items()))
    return out
