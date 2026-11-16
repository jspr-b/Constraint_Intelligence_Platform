/**
 * The flow editor's model (CI0005 seq 06): the found flow from the engine with the client's
 * edits laid over it, and the edit operations. Structure only: every share, count or assumed
 * share comes from the engine (GET /plants/{code}/flow); nothing here calculates a figure.
 */

import type { components } from "@/lib/api/schema";
import { INPUT, OUTPUT } from "./flowLayout";

export type Flow = components["schemas"]["FlowOut"];
export type Resource = components["schemas"]["ResourceOut"];
export type Edits = components["schemas"]["FlowEditsDoc-Input"];
export type Figure = Flow["arrows"][number]["share"];
export type StepKind = NonNullable<Edits["step_kinds"]>[number]["kind"];

export const EMPTY: Edits = {
  steps_added: [],
  routes_added: [],
  routes_wrong: [],
  route_names: [],
  touchpoints: [],
  merges: [],
  parallel: [],
  step_names: [],
  step_kinds: [],
  stations_added: [],
  station_names: [],
  stations_removed: [],
  step_stations: [],
  positions: [],
};

/** Every list present, so edits can spread without checks. */
export function full(e: Partial<Edits> | null | undefined): Required<Edits> {
  return { ...EMPTY, ...(e ?? {}) } as Required<Edits>;
}

export interface Step {
  code: string;
  name: string;
  kind: string;
  station: string | null;
  measured: boolean;
  added: boolean;
  parallel: number;
  jobs: number;
  missingFinish: number;
  rawCode: string | null;
  /** Codes merged into this step. */
  aliases: string[];
}

export interface Station {
  code: string;
  name: string;
  added: boolean;
}

export type ArrowKind = "measured" | "assumed" | "estimate" | "unknown" | "io";

export interface Arrow {
  id: string;
  from: string;
  to: string;
  kind: ArrowKind;
  jobs: number | null;
  /** Measured share, or the engine's assumed share for a route an added step split. */
  share: Figure | null;
  estimatePct: number | null;
  rework: boolean;
  lessCertain: boolean;
  uncertainJobs: number;
  wrong: boolean;
  added: boolean;
  name: string | null;
  routeId: string | null;
}

export interface TouchpointView {
  id: string;
  arrow: string;
  name: string;
  at: number;
  added: boolean;
}

export interface Model {
  steps: Step[];
  stations: Station[];
  arrows: Arrow[];
  touchpoints: TouchpointView[];
  /** Steps where a few jobs start or end, listed instead of drawn. */
  rare: { starts: { code: string; jobs: number }[]; ends: { code: string; jobs: number }[] };
}

export const key = (from: string, to: string) => `${from}>${to}`;

/** Below this share of jobs, a start or end is listed under the canvas instead of drawn. */
export const IO_MIN_PCT = 5;

export function buildModel(flow: Flow, resources: Resource[], raw: Edits): Model {
  const e = full(raw);
  const res = new Map(resources.map((r) => [r.resource_code, r]));
  const merged = new Map(e.merges.map((m) => [m.code, m.into]));
  const names = new Map(e.step_names.map((n) => [n.code, n.name]));
  const kinds = new Map(e.step_kinds.map((k) => [k.code, k.kind]));
  const parallel = new Map(e.parallel.map((p) => [p.code, p.places]));
  const stationOf = new Map(e.step_stations.map((s) => [s.code, s.station_code ?? null]));
  const removed = new Set(e.stations_removed);
  const station = (code: string, fallback: string | null) => {
    const s = stationOf.has(code) ? (stationOf.get(code) ?? null) : fallback;
    return s && !removed.has(s) ? s : null;
  };

  const steps: Step[] = flow.steps
    .filter((s) => !merged.has(s.code))
    .map((s) => {
      const r = res.get(s.code);
      return {
        code: s.code,
        name: names.get(s.code) ?? r?.name ?? s.code,
        kind: kinds.get(s.code) ?? r?.kind ?? "machine",
        station: station(s.code, r?.station_code ?? null),
        measured: true,
        added: false,
        parallel: parallel.get(s.code) ?? r?.parallel_units ?? 1,
        jobs: s.jobs,
        missingFinish: s.missing_finish,
        rawCode: s.code,
        aliases: e.merges.filter((m) => m.into === s.code).map((m) => m.code),
      };
    });
  for (const a of e.steps_added) {
    steps.push({
      code: a.code,
      name: names.get(a.code) ?? a.name,
      kind: kinds.get(a.code) ?? a.kind ?? "check",
      station: station(a.code, a.station_code ?? null),
      measured: false,
      added: true,
      parallel: parallel.get(a.code) ?? 1,
      jobs: 0,
      missingFinish: 0,
      rawCode: null,
      aliases: [],
    });
  }
  const codes = new Set(steps.map((s) => s.code));

  const stationNames = new Map(e.station_names.map((s) => [s.code, s.name]));
  const stations = new Map<string, Station>();
  for (const s of steps) {
    if (!s.station || stations.has(s.station)) continue;
    const r = resources.find((x) => x.station_code === s.station);
    stations.set(s.station, {
      code: s.station,
      name: stationNames.get(s.station) ?? r?.station_name ?? s.station,
      added: false,
    });
  }
  for (const s of e.stations_added) {
    if (removed.has(s.code)) continue;
    stations.set(s.code, { code: s.code, name: stationNames.get(s.code) ?? s.name, added: true });
  }

  const wrong = new Set(e.routes_wrong.map((r) => key(r.from_step, r.to_step)));
  const routeName = new Map(e.route_names.map((r) => [key(r.from_step, r.to_step), r.name]));
  const edited = new Map((flow.edited_arrows ?? []).map((a) => [key(a.from_step, a.to_step), a]));
  const split = new Set(
    e.steps_added.filter((s) => s.after && s.before).map((s) => key(s.after ?? "", s.before ?? "")),
  );
  const arrows: Arrow[] = [];
  const seen = new Set<string>();
  const push = (a: Arrow) => {
    if (seen.has(a.id) || !codes.has(a.from) || !codes.has(a.to)) return;
    seen.add(a.id);
    arrows.push(a);
  };
  for (const a of flow.arrows) {
    const k = key(a.from_step, a.to_step);
    if (split.has(k)) continue; // replaced by the step added on it; deleting that step brings it back
    push({
      id: k,
      from: a.from_step,
      to: a.to_step,
      kind: "measured",
      jobs: a.jobs,
      share: a.share,
      estimatePct: null,
      rework: a.rework,
      lessCertain: a.less_certain,
      uncertainJobs: a.uncertain_jobs,
      wrong: wrong.has(k),
      added: false,
      name: routeName.get(k) ?? null,
      routeId: null,
    });
  }
  const assumed = (from: string, to: string): Arrow => {
    const k = key(from, to);
    const server = edited.get(k);
    const share = server?.assumed_share ?? null;
    return {
      id: k,
      from,
      to,
      kind: share ? "assumed" : "unknown",
      jobs: server?.assumed_jobs ?? null,
      share,
      estimatePct: null,
      rework: false,
      lessCertain: false,
      uncertainJobs: 0,
      wrong: wrong.has(k),
      added: true,
      name: routeName.get(k) ?? null,
      routeId: null,
    };
  };
  for (const s of e.steps_added) {
    const measured = s.after && s.before && split.has(key(s.after, s.before));
    if (s.after) push(measured ? assumed(s.after, s.code) : unknownArrow(s.after, s.code));
    if (s.before) push(measured ? assumed(s.code, s.before) : unknownArrow(s.code, s.before));
  }
  for (const r of e.routes_added) {
    const k = key(r.from_step, r.to_step);
    push({
      ...unknownArrow(r.from_step, r.to_step),
      kind: r.estimate_pct ? "estimate" : "unknown",
      estimatePct: r.estimate_pct ?? null,
      wrong: wrong.has(k),
      name: routeName.get(k) ?? null,
      routeId: r.route_id,
    });
  }
  function unknownArrow(from: string, to: string): Arrow {
    const k = key(from, to);
    return {
      ...assumed(from, to),
      kind: "unknown",
      jobs: null,
      share: null,
      name: routeName.get(k) ?? null,
    };
  }

  // Input and Output: where many jobs start or end; the few others are listed.
  const many = (n: number) => 100 * n >= IO_MIN_PCT * flow.jobs;
  const rare: Model["rare"] = { starts: [], ends: [] };
  const target = (c: string) => merged.get(c) ?? c;
  const io = (from: string, to: string, jobs: number): Arrow => ({
    id: key(from, to),
    from,
    to,
    kind: "io",
    jobs,
    share: null,
    estimatePct: null,
    rework: false,
    lessCertain: false,
    uncertainJobs: 0,
    wrong: false,
    added: false,
    name: null,
    routeId: null,
  });
  codes.add(INPUT);
  codes.add(OUTPUT);
  for (const s of flow.steps) {
    const c = target(s.code);
    if (s.first_jobs) {
      if (many(s.first_jobs)) push(io(INPUT, c, s.first_jobs));
      else rare.starts.push({ code: c, jobs: s.first_jobs });
    }
    if (s.last_jobs) {
      if (many(s.last_jobs)) push(io(c, OUTPUT, s.last_jobs));
      else rare.ends.push({ code: c, jobs: s.last_jobs });
    }
  }
  for (const r of e.routes_added) {
    if (r.from_step === INPUT || r.to_step === OUTPUT) {
      const k = key(r.from_step, r.to_step);
      push({
        ...io(r.from_step, r.to_step, 0),
        kind: r.estimate_pct ? "estimate" : "unknown",
        jobs: null,
        estimatePct: r.estimate_pct ?? null,
        added: true,
        wrong: wrong.has(k),
        name: routeName.get(k) ?? null,
        routeId: r.route_id,
      });
    }
  }

  const touchpoints: TouchpointView[] = e.touchpoints
    .filter((t) => seen.has(key(t.from_step, t.to_step)))
    .map((t) => ({
      id: t.touchpoint_id,
      arrow: key(t.from_step, t.to_step),
      name: t.name,
      at: t.at ?? 0.5,
      added: true,
    }));
  return { steps, stations: [...stations.values()], arrows, touchpoints, rare };
}

/** Next free code for a step the client adds: NEW-01, NEW-02, … */
export function nextStepCode(e: Edits): string {
  const used = new Set(full(e).steps_added.map((s) => s.code));
  for (let i = 1; ; i++) {
    const c = `NEW-${String(i).padStart(2, "0")}`;
    if (!used.has(c)) return c;
  }
}

export function nextId(prefix: string, used: string[]): string {
  for (let i = 1; ; i++) {
    const c = `${prefix}${i}`;
    if (!used.includes(c)) return c;
  }
}

/** Replace the entry for `code` (or `from>to`) in one of the edit lists. */
export function upsert<T>(list: T[], same: (x: T) => boolean, item: T | null): T[] {
  const rest = list.filter((x) => !same(x));
  return item === null ? rest : [...rest, item];
}

export interface Problem {
  step: string;
  code: "not_connected" | "nothing_in" | "nothing_out" | "not_on_path" | "estimates_over";
  total?: number;
}

/**
 * Before Confirm: every step has a way in and out and lies on a path from Input to Output,
 * and the client's estimates out of one step add up to 100% at most.
 */
export function problems(model: Model): Problem[] {
  const live = model.arrows.filter((a) => !a.wrong);
  const reach = (start: string, forward: boolean) => {
    const seen = new Set([start]);
    const todo = [start];
    while (todo.length) {
      const id = todo.pop() as string;
      for (const a of live) {
        const [from, to] = forward ? [a.from, a.to] : [a.to, a.from];
        if (from === id && !seen.has(to)) {
          seen.add(to);
          todo.push(to);
        }
      }
    }
    return seen;
  };
  const fromInput = reach(INPUT, true);
  const toOutput = reach(OUTPUT, false);
  const out: Problem[] = [];
  for (const s of model.steps) {
    const ins = live.some((a) => a.to === s.code);
    const outs = live.some((a) => a.from === s.code);
    if (!ins && !outs) out.push({ step: s.code, code: "not_connected" });
    else if (!ins) out.push({ step: s.code, code: "nothing_in" });
    else if (!outs) out.push({ step: s.code, code: "nothing_out" });
    else if (!fromInput.has(s.code) || !toOutput.has(s.code))
      out.push({ step: s.code, code: "not_on_path" });
    const estimates = live
      .filter((a) => a.from === s.code && a.estimatePct != null)
      .reduce((sum, a) => sum + (a.estimatePct ?? 0), 0);
    if (estimates > 100) out.push({ step: s.code, code: "estimates_over", total: estimates });
  }
  return out;
}
