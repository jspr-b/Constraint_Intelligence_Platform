"""Hour bookings become touchpoints (ADR-0011 §5, CI0005 seq 05): a start and a duration give
start and end events at the booked times; a date and hours are placed in that day's shift and
marked estimated; a booking that cannot be placed is rejected with its reason, never guessed."""

from pathlib import Path

import yaml

from cip_connectors.importer import import_export
from cip_connectors.wizard import recognise_export
from cip_connectors.wizard.plan import Plan, PlanColumn, build_mapping, plan_from
from constraint_engine.detection import detect_periods
from constraint_engine.facts import measured_facts
from constraint_engine.figure import Confidence
from constraint_engine.io.plant_loader import load_plant

ROOT = Path(__file__).resolve().parents[3]
HOURS = ROOT / "data" / "synthetic" / "wizard_cases" / "ridder_hours"
STEPS = "Code;Naam\nLAS1;Welding\nLAK1;Paint\n"
SHIFTS = (
    "Werkplek;Type;Start;Einde\n"
    "LAS1;Dienst;20-07-2026 06:00;20-07-2026 14:00\n"
    "LAK1;Dienst;20-07-2026 07:00;20-07-2026 15:00\n"
)


def _rows(path: Path) -> list[dict[str, str]]:
    header, *lines = path.read_text().splitlines()
    return [dict(zip(header.split(","), line.split(","), strict=True)) for line in lines]


def _plan(booking_columns: list[PlanColumn], units: dict[tuple[str, str], str]) -> Plan:
    return Plan(
        tables={"uren.csv": "hour_bookings", "plekken.csv": "steps", "rooster.csv": "calendar"},
        columns=[
            *booking_columns,
            PlanColumn("uren.csv", "Order", ["events.order_id"]),
            PlanColumn("uren.csv", "Plek", ["events.resource_code"]),
            PlanColumn("uren.csv", "Gereed", ["events.quantity_units"]),
            PlanColumn("plekken.csv", "Code", ["resources.resource_code"]),
            PlanColumn("plekken.csv", "Naam", ["resources.name"]),
            PlanColumn("rooster.csv", "Werkplek", ["calendar.resource_code"]),
            PlanColumn("rooster.csv", "Type", ["calendar.kind"]),
            PlanColumn("rooster.csv", "Start", ["calendar.start_at"]),
            PlanColumn("rooster.csv", "Einde", ["calendar.end_at"]),
        ],
        meanings={"calendar.kind": {"Dienst": "shift"}},
        time_formats={
            ("uren.csv", "Datum"): "%d-%m-%Y",
            ("uren.csv", "Begin"): "%H:%M",
            ("rooster.csv", "Start"): "%d-%m-%Y %H:%M",
            ("rooster.csv", "Einde"): "%d-%m-%Y %H:%M",
        },
        units=units,  # type: ignore[arg-type]
        decimal=",",
    )


def _export(tmp_path: Path, bookings: str) -> Path:
    src = tmp_path / "in"
    src.mkdir()
    (src / "uren.csv").write_text(bookings)
    (src / "plekken.csv").write_text(STEPS)
    (src / "rooster.csv").write_text(SHIFTS)
    return src


def test_a_start_and_a_duration_become_a_start_and_an_end_at_the_booked_times(
    tmp_path: Path,
) -> None:
    src = _export(tmp_path, "Order;Plek;Datum;Begin;Duur;Gereed\nJ1;LAS1;20-07-2026;06:30;45;3\n")
    plan = _plan(
        [
            PlanColumn("uren.csv", "Datum", ["bookings.start_at"], "date"),
            PlanColumn("uren.csv", "Begin", ["bookings.start_at"], "time"),
            PlanColumn("uren.csv", "Duur", ["bookings.duration_min"]),
        ],
        {},
    )
    report = import_export(src, build_mapping(plan), tmp_path / "out")
    assert not report.row_errors, report.row_errors
    start, end = _rows(tmp_path / "out" / "events.csv")
    assert (start["event_type"], start["at"], start["time_source"]) == (
        "start",
        "2026-07-20T04:30:00Z",
        "booking",
    )
    assert (end["event_type"], end["at"], end["quantity_units"]) == (
        "end",
        "2026-07-20T05:15:00Z",
        "3",
    )
    assert start["event_id"] != end["event_id"]


def test_a_date_and_hours_are_placed_in_the_shift_one_after_another_and_marked_estimated(
    tmp_path: Path,
) -> None:
    src = _export(
        tmp_path,
        "Order;Plek;Datum;Uren;Gereed\n"
        "J1;LAK1;20-07-2026;1,5;3\n"
        "J2;LAK1;20-07-2026;2;4\n"
        "J3;LAS1;21-07-2026;1;1\n"  # no shift on LAS1 that day: rejected, never invented
        "J4;LAK1;20-07-2026;-1;1\n",
    )
    plan = _plan(
        [
            PlanColumn("uren.csv", "Datum", ["bookings.start_at"]),
            PlanColumn("uren.csv", "Uren", ["bookings.duration_min"]),
        ],
        {("uren.csv", "Uren"): "h"},
    )
    report = import_export(src, build_mapping(plan), tmp_path / "out")
    events = _rows(tmp_path / "out" / "events.csv")
    assert [(e["order_id"], e["event_type"], e["at"]) for e in events] == [
        ("J1", "start", "2026-07-20T05:00:00Z"),  # 07:00 Amsterdam: the shift start
        ("J1", "end", "2026-07-20T06:30:00Z"),
        ("J2", "start", "2026-07-20T06:30:00Z"),  # right after J1
        ("J2", "end", "2026-07-20T08:30:00Z"),
    ]
    assert {e["time_source"] for e in events} == {"estimated"}
    reasons = {(e.line, e.code, e.column) for e in report.row_errors}
    assert reasons == {(4, "no_shift_for_booking", "Datum"), (5, "not_a_duration", "Uren")}


def test_the_hours_only_export_reaches_its_answer_less_sure(tmp_path: Path) -> None:
    expected = yaml.safe_load((HOURS / "expected.yaml").read_text())
    found = recognise_export(sorted(p for p in HOURS.iterdir() if p.name != "expected.yaml"))
    report = import_export(HOURS, build_mapping(plan_from(found)), tmp_path)
    assert not report.row_errors and not report.missing_required
    plant = load_plant(tmp_path)
    assert {e.time_source for e in plant.events} == {"booking"}
    ((_, answer),) = detect_periods(plant, measured_facts(plant), (), kinds=("all",))
    own = {v: k for k, v in expected["code_tables"]["resource"].items()}
    assert answer.resource_code == own[expected["answer"]["constraint"]]
    assert answer.confidence.value < Confidence.HIGH.value
    (reason,) = [r for r in answer.reasons if r.code == "times_from_bookings"]
    assert reason.values["share_pct"] == 100.0
