"""SimPy flow-line simulation of a synthetic plant.

Orders arrive per product, follow their routing (second visits allowed), queue in front of
machines and block the upstream machine when the next queue is full. Machines only work in
available time: shifts minus uncovered breaks, planned maintenance and random breakdowns.
Every interval is logged so the true lost time per machine and cause is known.
"""

import math
import random
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from datetime import time, timedelta
from functools import partial
from typing import Any

import simpy

from constraint_engine.synthetic.calendar import Clock, MachineCalendar, build_calendars
from constraint_engine.synthetic.config import PlantCfg, ProductCfg
from constraint_engine.synthetic.intervals import Interval, normalise, subtract, total

NEVER = 10.0**9


@dataclass
class MachineLog:
    running: list[Interval] = field(default_factory=list)
    setup: list[Interval] = field(default_factory=list)
    blocked: list[Interval] = field(default_factory=list)
    downs: list[tuple[float, float, str]] = field(default_factory=list)
    scrap_run_min: list[tuple[float, float]] = field(default_factory=list)
    """(minute, run minutes spent on units later scrapped)."""
    units_out: list[tuple[float, int]] = field(default_factory=list)


@dataclass
class SimOrder:
    order_id: str
    product: ProductCfg
    quantity: int
    arrival: float | None
    due: float
    good_quantity: int = 0
    started: bool = False
    shipped: float | None = None


@dataclass
class SimResult:
    cfg: PlantCfg
    clock: Clock
    calendars: dict[str, MachineCalendar]
    availability: dict[str, list[Interval]]
    logs: dict[str, MachineLog]
    orders: list[SimOrder]
    events: list[dict[str, Any]]
    history_end: float


class Availability:
    """Available time of one machine, as sorted disjoint intervals."""

    def __init__(self, intervals: list[Interval]) -> None:
        self.iv = normalise(intervals)

    def window_at(self, t: float) -> Interval | None:
        """The available interval containing ``t``, or the next one after it."""
        for start, end in self.iv:
            if end > t:
                return (max(start, t), end)
        return None


class Simulation:
    def __init__(self, cfg: PlantCfg) -> None:
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.clock = Clock.for_plant(cfg)
        self.history_end = self.clock.minute(
            cfg.start_date + timedelta(weeks=cfg.weeks_history), time(0, 0)
        )
        weeks = cfg.weeks_history + cfg.weeks_orderbook
        self.calendars = build_calendars(cfg, self.clock, weeks)
        self.logs = {r.code: MachineLog() for r in cfg.resources}
        self.events: list[dict[str, Any]] = []
        self.availability = {code: self._availability(code) for code in self.logs}
        self.env = simpy.Environment()
        self.machines = {r.code: simpy.Resource(self.env, capacity=1) for r in cfg.resources}
        self.queues = {
            r.code: simpy.Resource(self.env, capacity=r.buffer_orders) for r in cfg.resources
        }
        self.last_family: dict[str, str | None] = {code: None for code in self.logs}
        self.orders: list[SimOrder] = []

    # ------------------------------------------------------------------ calendar and downs
    def _production_time(self, code: str) -> list[Interval]:
        """Shift time in history, minus uncovered breaks and planned maintenance."""
        cal = self.calendars[code]
        working = subtract(subtract(cal.shifts, cal.uncovered_breaks()), cal.maintenance)
        return subtract(working, [(self.history_end, NEVER)])

    def _availability(self, code: str) -> list[Interval]:
        res = self.cfg.resource(code)
        production = self._production_time(code)
        if res.downs_per_week > 0 and production:
            mean_gap = total(production) / self.cfg.weeks_history / res.downs_per_week
            self._place_downs(code, production, mean_gap)
        for start, end in self.calendars[code].maintenance:
            if start < self.history_end:
                self.logs[code].downs.append((start, end, "PM"))
        downs = [(s, e) for s, e, reason in self.logs[code].downs if reason != "PM"]
        return subtract(production, downs)

    def _place_downs(self, code: str, production: list[Interval], mean_gap: float) -> None:
        res = self.cfg.resource(code)
        until_next = self.rng.expovariate(1 / mean_gap)
        for start, end in production:
            cursor = start
            while cursor + until_next < end:
                down_start = cursor + until_next
                duration = max(5.0, self.rng.expovariate(1 / res.down_mean_min))
                down_end = min(down_start + duration, end)
                self.logs[code].downs.append(
                    (down_start, down_end, self.rng.choice(res.down_reasons))
                )
                cursor = down_end
                until_next = self.rng.expovariate(1 / mean_gap)
            until_next -= end - cursor

    # ------------------------------------------------------------------ helpers
    def _noise(self, cv: float) -> float:
        if cv <= 0:
            return 1.0
        sigma = math.sqrt(math.log(1 + cv * cv))
        return self.rng.lognormvariate(-sigma * sigma / 2, sigma)

    def _poisson(self, lam: float) -> int:
        limit, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= limit:
                return k
            k += 1

    def _emit(self, event_type: str, at: float, **fields: Any) -> None:
        self.events.append({"event_type": event_type, "at": at, **fields})

    def consume(
        self,
        code: str,
        minutes: float,
        sink: list[Interval],
        on_start: Callable[[float], None] | None = None,
    ) -> Generator[Any, Any, list[Interval]]:
        """Work ``minutes`` of machine time, pausing outside available time.

        Each chunk is logged in ``sink`` when it starts, so work still in progress when the
        history ends is counted too.
        """
        avail = Availability(self.availability[code])
        segments: list[Interval] = []
        remaining = minutes
        while remaining > 1e-9:
            window = avail.window_at(self.env.now)
            if window is None:
                yield self.env.timeout(NEVER)
                return segments
            if window[0] > self.env.now:
                yield self.env.timeout(window[0] - self.env.now)
            chunk = min(remaining, window[1] - self.env.now)
            if not segments and on_start is not None:
                on_start(self.env.now)
            segments.append((self.env.now, self.env.now + chunk))
            sink.append(segments[-1])
            yield self.env.timeout(chunk)
            remaining -= chunk
        return segments

    # ------------------------------------------------------------------ orders
    def _arrivals(self, week: int, product: ProductCfg) -> list[float]:
        week_start, week_end = (week - 1) * 7 * 1440.0, week * 7 * 1440.0
        shifts = [
            i
            for i in self.calendars[product.steps[0].resource].shifts
            if week_start <= i[0] < week_end
        ]
        n = self._poisson(self.cfg.orders_per_week(product.sku, week))
        if not shifts:
            return []
        out = []
        for _ in range(n):
            start, end = self.rng.choice(shifts)
            out.append(self.rng.uniform(start, end))
        return sorted(out)

    def _create_orders(self) -> None:
        arrivals: list[tuple[float, ProductCfg]] = []
        if self.cfg.initial_backlog_weeks > 0:
            for product in self.cfg.products:
                n = self._poisson(
                    self.cfg.orders_per_week(product.sku, 1) * self.cfg.initial_backlog_weeks
                )
                arrivals += [(0.0, product)] * n
        for week in range(1, self.cfg.weeks_history + self.cfg.weeks_orderbook + 1):
            for product in self.cfg.products:
                arrivals += [(t, product) for t in self._arrivals(week, product)]
        arrivals.sort(key=lambda a: (a[0], a[1].sku))
        for n, (t, product) in enumerate(arrivals):
            order = SimOrder(
                order_id=f"SO-{24000 + n:05d}",
                product=product,
                quantity=self.rng.randint(product.qty_min, product.qty_max),
                arrival=t if t < self.history_end else None,
                due=t + product.due_days * 1440,
            )
            self.orders.append(order)
            if order.arrival is not None:
                self.env.process(self._run_order(order))

    def _station(self, code: str) -> str:
        return self.cfg.resource(code).station

    def _run_order(self, order: SimOrder) -> Generator[Any, Any, None]:
        assert order.arrival is not None
        yield self.env.timeout(order.arrival)
        first = order.product.steps[0].resource
        self._emit("scan", self.env.now, station_code=self._station(first), order_id=order.order_id)
        qty, slot = order.quantity, None
        per_unit: list[tuple[str, float]] = []
        for i, step in enumerate(order.product.steps):
            with self.machines[step.resource].request() as machine:
                yield machine
                if slot is not None:
                    self.queues[step.resource].release(slot)
                order.started = True
                yield from self._setup(step.resource, step.setup_min, order.product.setup_family)
                run = step.run_min_per_unit * qty * self._noise(step.cv)
                common: dict[str, Any] = {
                    "resource_code": step.resource,
                    "order_id": order.order_id,
                    "operation_seq": (i + 1) * 10,
                    "quantity_units": qty,
                }
                segs = yield from self.consume(
                    step.resource,
                    run,
                    self.logs[step.resource].running,
                    on_start=partial(self._emit, "start", **common),
                )
                self._emit("end", segs[-1][1], **common)
                per_unit.append((step.resource, run / qty))
                qty = self._scrap(step.resource, segs, order, i + 1, qty, per_unit)
                if i + 1 < len(order.product.steps):
                    nxt = order.product.steps[i + 1].resource
                    slot = yield from self._wait_for_queue(step.resource, nxt, order)
        order.good_quantity = qty
        order.shipped = self.env.now
        self.logs[order.product.steps[-1].resource].units_out.append((self.env.now, qty))

    def _setup(self, code: str, setup_min: float, family: str) -> Generator[Any, Any, None]:
        previous, self.last_family[code] = self.last_family[code], family
        if setup_min <= 0 or previous is None or previous == family:
            return
        segs = yield from self.consume(
            code,
            setup_min * self._noise(0.2),
            self.logs[code].setup,
            on_start=lambda t: self._emit("setup_start", t, resource_code=code),
        )
        self._emit("setup_end", segs[-1][1], resource_code=code)

    def _scrap(
        self,
        code: str,
        segs: list[Interval],
        order: SimOrder,
        seq: int,
        qty: int,
        per_unit: list[tuple[str, float]],
    ) -> int:
        rule = next((s for s in self.cfg.scrap if s.found_at == code), None)
        if rule is None or not segs:
            return qty
        scrapped = sum(1 for _ in range(qty) if self.rng.random() < rule.rate)
        if scrapped == 0:
            return qty
        at = segs[-1][1]
        self._emit(
            "scrap",
            at,
            resource_code=code,
            order_id=order.order_id,
            operation_seq=seq * 10,
            scrap_units=scrapped,
            scrap_reason_code=rule.reason,
        )
        for machine, minutes in per_unit:
            self.logs[machine].scrap_run_min.append((at, minutes * scrapped))
        return qty - scrapped

    def _wait_for_queue(self, here: str, nxt: str, order: SimOrder) -> Generator[Any, Any, Any]:
        waited_from = self.env.now
        slot = self.queues[nxt].request()
        yield slot
        if self.env.now > waited_from:
            self.logs[here].blocked.append((waited_from, self.env.now))
        self._emit("scan", self.env.now, station_code=self._station(nxt), order_id=order.order_id)
        return slot

    # ------------------------------------------------------------------ run
    def run(self) -> SimResult:
        self._create_orders()
        self.env.run(until=self.history_end)
        for code, log in self.logs.items():
            for start, end, reason in log.downs:
                self._emit("down_start", start, resource_code=code, down_reason_code=reason)
                self._emit("down_end", end, resource_code=code, down_reason_code=reason)
        self.events.sort(key=lambda e: (e["at"], e["event_type"]))
        for n, event in enumerate(self.events):
            event["event_id"] = f"E{n + 1:07d}"
        return SimResult(
            cfg=self.cfg,
            clock=self.clock,
            calendars=self.calendars,
            availability=self.availability,
            logs=self.logs,
            orders=self.orders,
            events=self.events,
            history_end=self.history_end,
        )


def simulate(cfg: PlantCfg) -> SimResult:
    return Simulation(cfg).run()
