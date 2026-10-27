"""Codes and formats of an unseen export (ADR-0011 §4, CI0005 sequence 04)."""

from pathlib import Path

import pytest

from cip_connectors.wizard import recognise_export
from cip_connectors.wizard.codes import meaning_of

STEPS = "Code;Omschrijving;Soort\nLAS1;Welding;Machine\nLAK1;Paint;Machine\nMONT;Assembly;Hand\n"
SHIFTS = "Werkplek;Type;Start;Einde\n" + "".join(
    f"{c};Dienst;0{d}-08-2026 06:00;0{d}-08-2026 14:00\n"
    for d in range(1, 8)
    for c in ("LAS1", "LAK1")
)


def _export(tmp_path: Path, log: str, steps: str = STEPS, shifts: str = SHIFTS) -> list[Path]:
    for name, text in (("scans.csv", log), ("werkplekken.csv", steps), ("rooster.csv", shifts)):
        (tmp_path / name).write_text(text, encoding="utf-8")
    return sorted(tmp_path.iterdir())


def _log(statuses: list[str], stamp: str = "{d:02d}-08-2026 06:{m:02d}") -> str:
    rows = ["Werkplek;Bon;Status;Tijdstip;Aantal"]
    for i in range(60):
        when = stamp.format(d=1 + i % 9, m=i % 60)
        step, status = ["LAS1", "LAK1"][i % 2], statuses[i % len(statuses)]
        rows.append(f"{step};{24000 + i // 2};{status};{when};{i % 7}")
    return "\n".join(rows) + "\n"


@pytest.mark.parametrize(
    ("code", "meaning", "sure"),
    [
        ("GEREED", "end", "sure"),
        ("Clock on", "start", "sure"),
        ("OMSTEL_START", "setup_start", "sure"),
        ("STORING_EINDE", "down_end", "sure"),
        ("RUEST_A", "setup_start", "likely"),
        ("ANK", "scan", "likely"),
        ("XQ7", None, None),
    ],
)
def test_an_event_code_means_what_its_words_say(code: str, meaning: str | None, sure: str) -> None:
    assert meaning_of("events.event_type", code)[:2] == (meaning, sure)


def test_an_unknown_code_is_kept_and_asked_never_dropped(tmp_path: Path) -> None:
    found = recognise_export(_export(tmp_path, _log(["GESTART", "GEREED", "XQ7"])))
    codes = {c.code: c for c in found.codes if c.target == "events.event_type"}
    assert set(codes) == {"GESTART", "GEREED", "XQ7"}
    assert codes["XQ7"].meaning is None and codes["XQ7"].sure is None
    assert codes["XQ7"].rows == 20
    assert "XQ7" not in found.code_tables()["events.event_type"]


def test_steps_keep_the_plants_codes_with_name_and_kind(tmp_path: Path) -> None:
    found = recognise_export(_export(tmp_path, _log(["GESTART", "GEREED"])))
    steps = {s.code: (s.name, s.kind) for s in found.steps}
    assert steps == {
        "LAS1": ("Welding", "machine"),
        "LAK1": ("Paint", "machine"),
        "MONT": ("Assembly", "manual"),
    }


def test_a_day_above_12_tells_the_date_order(tmp_path: Path) -> None:
    found = recognise_export(_export(tmp_path, _log(["GESTART", "GEREED"])))
    # The log's days are 1-9, but the shift sheet is written the same way: still day 1-7.
    # Day-month comes from nowhere, so it is asked for both.
    asked = [t for t in found.formats.times if t.format is None]
    assert {t.table for t in asked} == {"scans.csv", "rooster.csv"}
    assert all(t.options == ["%d-%m-%Y %H:%M", "%m-%d-%Y %H:%M"] for t in asked)
    later = SHIFTS.replace("07-08-2026", "17-08-2026")
    found = recognise_export(_export(tmp_path, _log(["GESTART", "GEREED"]), shifts=later))
    assert {t.format for t in found.formats.times} == {"%d-%m-%Y %H:%M"}
    assert all(t.sure == "sure" for t in found.formats.times)


def test_month_day_from_a_us_export(tmp_path: Path) -> None:
    log = _log(["Clock on", "Clock off"], stamp="08/{d:02d}/2026 06:{m:02d}").replace(
        "08/09/2026", "08/19/2026"
    )
    found = recognise_export(_export(tmp_path, log))
    scans = next(t for t in found.formats.times if t.table == "scans.csv")
    assert scans.format == "%m/%d/%Y %H:%M"


def _overtime(hours: list[str], name: str = "Uren") -> str:
    rows = [f"Werkplek;Jaar;Week;{name}"]
    rows += [
        f"{c};2026;{w};{hours[w % len(hours)]}" for w in range(27, 40) for c in ("LAS1", "LAK1")
    ]
    return "\n".join(rows) + "\n"


def test_decimal_comma_and_both_marks_asked(tmp_path: Path) -> None:
    _export(tmp_path, _log(["GESTART", "GEREED"]))
    (tmp_path / "overuren.csv").write_text(_overtime(["7,5", "8,25"]), encoding="utf-8")
    found = recognise_export(sorted(tmp_path.iterdir()))
    assert (found.formats.decimal, found.formats.decimal_sure) == (",", "sure")
    (tmp_path / "overuren.csv").write_text(_overtime(["7,5", "8.25"]), encoding="utf-8")
    found = recognise_export(sorted(tmp_path.iterdir()))
    assert found.formats.decimal_sure is None


def test_a_duration_takes_its_unit_from_the_column_name(tmp_path: Path) -> None:
    _export(tmp_path, _log(["GESTART", "GEREED"]))
    (tmp_path / "overuren.csv").write_text(_overtime(["7", "8"], "Overuren"), encoding="utf-8")
    found = recognise_export(sorted(tmp_path.iterdir()))
    (unit,) = found.formats.units
    assert (unit.column, unit.unit, unit.sure) == ("Overuren", "h", "sure")


def test_every_meaning_a_word_gives_is_a_meaning_the_schema_has() -> None:
    from cip_connectors.wizard.codes import MEANINGS, WORDS
    from cip_schema.master import CalendarKind, ResourceKind
    from cip_schema.transactional import EventType, OrderStatus

    assert set(MEANINGS["events.event_type"]) == {e.value for e in EventType}
    assert set(MEANINGS["orders.status"]) == {s.value for s in OrderStatus}
    assert set(MEANINGS["calendar.kind"]) == {k.value for k in CalendarKind}
    assert set(MEANINGS["resources.kind"]) <= {k.value for k in ResourceKind}
    for target, words in WORDS.items():
        assert set(words) <= set(MEANINGS[target]), target
