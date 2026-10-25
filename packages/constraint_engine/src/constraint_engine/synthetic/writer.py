"""Write a simulated plant in the standard layout (see docs/plant_layout.md)."""

import csv
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml

from constraint_engine.synthetic.expected import expected_answers
from constraint_engine.synthetic.model import SimResult
from constraint_engine.synthetic.truth import generator_log, pooled

EVENT_COLUMNS = (
    "event_id",
    "event_type",
    "at",
    "resource_code",
    "station_code",
    "order_id",
    "operation_seq",
    "quantity_units",
    "scrap_units",
    "down_reason_code",
    "scrap_reason_code",
)


def _ts(result: SimResult, minute: float) -> str:
    moment = result.clock.at(round(minute * 60) / 60)
    return moment.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: "" if row.get(c) is None else row.get(c) for c in columns})


def _master(result: SimResult, out: Path) -> None:
    cfg = result.cfg
    (out / "plant.json").write_text(
        json.dumps(
            {"plant_code": cfg.plant_code, "name": cfg.name, "timezone_iana": cfg.timezone},
            indent=2,
        )
        + "\n"
    )
    _csv(
        out / "stations.csv",
        ("station_code", "name"),
        [{"station_code": k, "name": v} for k, v in cfg.stations.items()],
    )
    _csv(
        out / "resources.csv",
        ("resource_code", "name", "station_code", "kind", "parallel_units"),
        [
            {
                "resource_code": r.code,
                "name": r.name,
                "station_code": r.station,
                "kind": r.kind,
                "parallel_units": max(cfg.positions(r.code)),
            }
            for r in cfg.resources
        ],
    )
    if cfg.teams:
        _csv(
            out / "teams.csv",
            ("team_code", "name", "resource_codes"),
            [
                {"team_code": t.code, "name": t.name, "resource_codes": ";".join(t.steps)}
                for t in cfg.teams
            ],
        )
    if not cfg.export.products:
        return  # ADR-0009: the plant shares no products or routings
    _csv(
        out / "products.csv",
        (
            "sku",
            "name",
            "family",
            "setup_family",
            "sales_price_eur_cents",
            "truly_variable_cost_eur_cents",
        ),
        [
            {
                "sku": p.sku,
                "name": p.name,
                "family": p.family,
                "setup_family": p.setup_family,
                "sales_price_eur_cents": p.price_eur_cents,
                "truly_variable_cost_eur_cents": p.tvc_eur_cents,
            }
            for p in cfg.products
        ],
    )
    routing_rows, ops, changeovers = [], {}, {}
    for p in cfg.products:
        for i, s in enumerate(p.steps):
            erp_run = s.erp_run_min_per_unit or s.run_min_per_unit
            routing_rows.append(
                {
                    "sku": p.sku,
                    "operation_seq": (i + 1) * 10,
                    "operation": s.operation,
                    "resource_code": s.resource,
                    "alternative_resource_codes": ";".join(s.alternatives),
                    "standard_setup_min": s.erp_setup_min
                    if s.erp_setup_min is not None
                    else s.setup_min or None,
                    "standard_run_min_per_unit": erp_run,
                }
            )
            for code in (s.resource, *s.alternatives):
                ops[(code, s.operation)] = erp_run
            if s.setup_min > 0:
                for q in cfg.products:
                    if q.setup_family != p.setup_family and any(
                        t.resource == s.resource for t in q.steps
                    ):
                        changeovers[(s.resource, q.setup_family, p.setup_family)] = s.setup_min
    _csv(
        out / "routings.csv",
        (
            "sku",
            "operation_seq",
            "operation",
            "resource_code",
            "alternative_resource_codes",
            "standard_setup_min",
            "standard_run_min_per_unit",
        ),
        routing_rows,
    )
    _csv(
        out / "resource_operations.csv",
        ("resource_code", "operation", "standard_run_min_per_unit"),
        [
            {"resource_code": c, "operation": o, "standard_run_min_per_unit": v}
            for (c, o), v in sorted(ops.items())
        ],
    )
    _csv(
        out / "changeovers.csv",
        ("resource_code", "from_setup_family", "to_setup_family", "changeover_min"),
        [
            {"resource_code": c, "from_setup_family": f, "to_setup_family": t, "changeover_min": v}
            for (c, f, t), v in sorted(changeovers.items())
        ],
    )


def _capacity(result: SimResult, out: Path) -> None:
    cfg, rows = result.cfg, []
    staffed = any(pooled(result, code) for code in result.calendars)
    for code, cal in result.calendars.items():
        if staffed:  # one row per shift, with its staffed positions
            rows += [
                {
                    "resource_code": code,
                    "kind": "shift",
                    "start_at": _ts(result, s),
                    "end_at": _ts(result, e),
                    "covered": "false",
                    "positions": cfg.positions(code)[i],
                }
                for i, (s, e) in result.shift_windows
            ]
        else:
            rows += [
                {
                    "resource_code": code,
                    "kind": "shift",
                    "start_at": _ts(result, s),
                    "end_at": _ts(result, e),
                    "covered": "false",
                }
                for s, e in cal.shifts
            ]
        rows += [
            {
                "resource_code": code,
                "kind": "break",
                "start_at": _ts(result, b.start),
                "end_at": _ts(result, b.end),
                "covered": str(b.covered).lower(),
            }
            for b in cal.breaks
        ]
        rows += [
            {
                "resource_code": code,
                "kind": "maintenance",
                "start_at": _ts(result, s),
                "end_at": _ts(result, e),
                "covered": "false",
            }
            for s, e in cal.maintenance
        ]
    columns = ("resource_code", "kind", "start_at", "end_at", "covered")
    _csv(out / "calendar.csv", (*columns, "positions") if staffed else columns, rows)
    if cfg.teams:
        _csv(
            out / "team_shifts.csv",
            ("team_code", "start_at", "end_at", "positions"),
            [
                {
                    "team_code": t.code,
                    "start_at": _ts(result, s),
                    "end_at": _ts(result, e),
                    "positions": t.positions[i],
                }
                for t in cfg.teams
                for i, (s, e) in result.shift_windows
            ],
        )
    overtime = []
    for o in cfg.overtime:
        iso = (cfg.start_date + timedelta(weeks=o.week - 1)).isocalendar()
        overtime.append(
            {
                "resource_code": o.resource,
                "iso_year": iso.year,
                "iso_week": iso.week,
                "overtime_h": o.overtime_h,
            }
        )
    _csv(out / "overtime.csv", ("resource_code", "iso_year", "iso_week", "overtime_h"), overtime)
    _csv(
        out / "capacity_costs.csv",
        ("resource_code", "overtime_eur_cents_per_h", "extra_shift_eur_cents"),
        [
            {
                "resource_code": r.code,
                "overtime_eur_cents_per_h": r.overtime_eur_cents_per_h,
                "extra_shift_eur_cents": r.extra_shift_eur_cents,
            }
            for r in cfg.resources
            if r.overtime_eur_cents_per_h or r.extra_shift_eur_cents
        ],
    )
    _csv(
        out / "outsourcing.csv",
        ("operation", "sku", "price_eur_cents_per_unit"),
        [
            {"operation": o.operation, "price_eur_cents_per_unit": o.price_eur_cents_per_unit}
            for o in cfg.outsourcing
        ],
    )


def _orders_and_events(result: SimResult, out: Path) -> None:
    rows = []
    products = result.cfg.export.products
    for o in result.orders:
        status = (
            "shipped"
            if o.shipped is not None
            else "in_progress"
            if o.started
            else ("released" if o.arrival is not None else "open")
        )
        created = o.arrival if o.arrival is not None else o.due - o.product.due_days * 1440
        rows.append(
            {
                "order_id": o.order_id,
                "sku": o.product.sku if products else None,
                "quantity_units": o.quantity,
                "due_at": _ts(result, o.due),
                "status": status,
                "released_at": _ts(result, o.arrival) if o.arrival is not None else None,
                "shipped_at": _ts(result, o.shipped) if o.shipped is not None else None,
                "material_ready_at": _ts(result, created),
                "order_value_eur_cents": o.quantity * o.product.price_eur_cents,
                "material_cost_eur_cents": o.quantity * o.product.tvc_eur_cents,
            }
        )
    columns = (
        "order_id",
        "sku",
        "quantity_units",
        "due_at",
        "status",
        "released_at",
        "shipped_at",
        "material_ready_at",
    )
    value = ("order_value_eur_cents", "material_cost_eur_cents")
    _csv(out / "orders.csv", columns if products else (*columns, *value), rows)
    numbers = result.cfg.export.step_numbers
    events = [
        {**e, "at": _ts(result, e["at"]), **({} if numbers else {"operation_seq": None})}
        for e in result.events
    ]
    _csv(out / "events.csv", EVENT_COLUMNS, events)


def write_plant(result: SimResult, out: Path | str) -> Path:
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    _master(result, root)
    _capacity(result, root)
    _orders_and_events(result, root)
    answers = expected_answers(result).model_dump(mode="json")
    for extra in (
        "constraint_type",
        "constraint_covers",
        "forgotten_end_scan_share_pct",
        "throughput_eur_cents_per_constraint_h_by_month",
    ):
        if answers[extra] is None:
            del answers[extra]
    (root / "expected_answers.yaml").write_text(
        yaml.safe_dump(answers, sort_keys=False, allow_unicode=True)
    )
    (root / "generator_log.json").write_text(
        json.dumps(generator_log(result), indent=2, sort_keys=True) + "\n"
    )
    return root
