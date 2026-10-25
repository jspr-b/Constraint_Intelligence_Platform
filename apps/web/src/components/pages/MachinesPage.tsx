"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState, type ReactNode } from "react";
import { ConstraintMarker, isMissing, MicroLabel, Panel, type FigureLike } from "@cip/ui";
import { api } from "@/lib/api/client";
import { ConstraintBanner, useDetection } from "../ConstraintBanner";
import { useDetails } from "../Details";
import { useFacts, useTeams, valueOf, type Fact, type Period } from "../diagnose";
import { EmptyState } from "../EmptyState";
import { Figure, HowCalculated } from "../Figure";
import { PageHeader } from "../PageHeader";
import { PlantPicker, usePlant } from "../PlantPicker";
import { Term } from "../Term";
import { termTags } from "../terms";

const TH =
  "px-3 py-2 text-left text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted [&_button]:uppercase";
const TD = "px-3 py-2 align-top";

/** Columns of the overview: [key, fact family, measure]. */
const COLUMNS = [
  ["busy", "utilisation", "utilisation_pct"],
  ["running", "state_share", "running_pct"],
  ["setup", "state_share", "setup_pct"],
  ["down", "state_share", "down_pct"],
  ["starved", "state_share", "starved_pct"],
  ["blocked", "state_share", "blocked_pct"],
  ["planned", "state_share", "break_pct"],
  ["maintenance", "state_share", "maintenance_pct"],
  ["unknown", "state_share", "unknown_pct"],
  ["oee", "oee", "oee_ratio"],
  ["capacity", "effective_capacity", "effective_capacity_h"],
] as const;
type ColumnKey = (typeof COLUMNS)[number][0] | "machine";

/** Timeline order and colour per state (always with a label: never colour alone). */
const TIMELINE: [string, string][] = [
  ["running", "bg-ok"],
  ["setup", "bg-accent"],
  ["down", "bg-bad"],
  ["blocked", "bg-warn"],
  ["starved", "bg-idle"],
  ["break", "bg-line-strong"],
  ["maintenance", "bg-faint"],
  ["unknown", "bg-raised"],
];

/** Header terms that have a glossary entry. */
const TERM_OF: Partial<Record<ColumnKey, "setup" | "starved" | "blocked" | "oee" | "capacity">> = {
  setup: "setup",
  starved: "starved",
  blocked: "blocked",
  oee: "oee",
  capacity: "capacity",
};

function MachineName({ name, code }: { name: string; code: string }) {
  return (
    <span className="px-1">
      <span className="font-medium">{name}</span>{" "}
      <span className="font-mono text-xs text-muted" data-raw>
        {code}
      </span>
    </span>
  );
}

/** A figure with a confidence mark when it is less than high. */
function Cell({ fact, label }: { fact: Fact | undefined; label: string }) {
  const t = useTranslations("figure");
  if (!fact) return <span className="text-faint">—</span>;
  const weak = fact.figure.confidence !== "high" && !isMissing(fact.figure.value);
  return (
    <span className="inline-flex items-baseline gap-1">
      <Figure figure={fact.figure as FigureLike} label={label} />
      {weak && (
        <span
          className="text-xs text-warn"
          title={t(`level.${fact.figure.confidence}`)}
          aria-label={t(`level.${fact.figure.confidence}`)}
        >
          ◆
        </span>
      )}
    </span>
  );
}

/** Machines page: how busy each machine really is, from the measured facts (sequence 06). */
export function MachinesPage() {
  const t = useTranslations("machines");
  const locale = useLocale();
  const picker = usePlant();
  const { plant } = picker;
  const [periodKey, setPeriodKey] = useState("all");
  const [sort, setSort] = useState<{ key: ColumnKey; desc: boolean }>({ key: "busy", desc: true });
  const [open, setOpen] = useState<string | null>(null);

  const periods = useQuery({
    queryKey: ["fact-periods", plant],
    enabled: plant !== null,
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/facts/periods", {
          params: { path: { plant_code: plant ?? "" } },
        })
      ).data ?? [],
  });
  const teams = useTeams(plant);
  const resources = useQuery({
    queryKey: ["resources", plant],
    enabled: plant !== null,
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/resources", {
          params: { path: { plant_code: plant ?? "" } },
        })
      ).data ?? [],
  });
  const chosen: Period | undefined = (periods.data ?? []).find(
    (p) => `${p.period_kind}:${p.period_start_at}` === periodKey,
  );
  const periodQuery = chosen
    ? { period_kind: chosen.period_kind, period_start_at: chosen.period_start_at }
    : { period_kind: "all" as const };
  const facts = useFacts(plant, {
    family: ["utilisation", "state_share", "oee", "effective_capacity"],
    ...periodQuery,
  });
  const detection = useDetection(
    plant,
    chosen && chosen.period_kind !== "day"
      ? { period_kind: chosen.period_kind, period_start_at: chosen.period_start_at }
      : { period_kind: "all" },
  );
  const found = detection.data?.detections[0];
  const loss = useFacts(
    plant,
    {
      family: ["loss"],
      ...(found ? { period_kind: found.period_kind, period_start_at: found.period_start_at } : {}),
    },
    found?.kind === "internal",
  );
  const bottleneck = found?.resource_code ?? null;

  const date = (iso: string) =>
    new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(iso));
  const periodName = (p: Period | undefined) =>
    !p || p.period_kind === "all"
      ? t("periodAll")
      : p.period_kind === "month"
        ? new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(
            new Date(p.period_start_at),
          )
        : t("periodWeek", { date: date(p.period_start_at) });

  const names = new Map([
    ...(resources.data ?? []).map((r) => [r.resource_code, r.name] as const),
    ...teams.map((team) => [team.team_code, team.name] as const),
  ]);
  const label = (code: string) => `${names.get(code) ?? code} (${code})`;
  const byMachine = useMemo(() => {
    const out = new Map<string, Map<string, Fact>>();
    for (const f of facts.data?.facts ?? []) {
      const row = out.get(f.resource_code) ?? new Map<string, Fact>();
      row.set(f.measure, f);
      out.set(f.resource_code, row);
    }
    return out;
  }, [facts.data]);

  const measureOf = (key: ColumnKey) => COLUMNS.find(([k]) => k === key)?.[2];
  const rows = [...byMachine.entries()].sort(([a, fa], [b, fb]) => {
    if (sort.key === "machine") return sort.desc ? b.localeCompare(a) : a.localeCompare(b);
    const m = measureOf(sort.key) ?? "";
    const va = valueOf(fa.get(m)) ?? -Infinity;
    const vb = valueOf(fb.get(m)) ?? -Infinity;
    return sort.desc ? vb - va : va - vb;
  });
  const busiest = [...byMachine.entries()].sort(
    ([, a], [, b]) =>
      (valueOf(b.get("utilisation_pct")) ?? -1) - (valueOf(a.get("utilisation_pct")) ?? -1),
  )[0]?.[0];

  const run = facts.data?.run;
  const header = (
    <PageHeader
      page="machines"
      headline={
        run?.status !== "ready" ? undefined : found ? (
          <span data-raw>
            {bottleneck ? t("headlineConstraint", { name: label(bottleneck) }) : t("headlineNone")}
          </span>
        ) : busiest ? (
          <span data-raw>{t("headline", { name: label(busiest) })}</span>
        ) : undefined
      }
      actions={
        <>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted">{t("period")}</span>
            <select
              value={periodKey}
              onChange={(e) => {
                setPeriodKey(e.target.value);
                setOpen(null);
              }}
              className="rounded-control border border-line-strong bg-surface px-2 py-1 text-sm"
              data-raw
            >
              <option value="all">{t("periodAll")}</option>
              {(periods.data ?? [])
                .filter((p) => p.period_kind === "month" || p.period_kind === "week")
                .map((p) => (
                  <option
                    key={`${p.period_kind}:${p.period_start_at}`}
                    value={`${p.period_kind}:${p.period_start_at}`}
                  >
                    {periodName(p)}
                  </option>
                ))}
            </select>
          </label>
          <PlantPicker {...picker} />
        </>
      }
    />
  );

  if (picker.plants && picker.plants.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        {header}
        <EmptyState title={t("noPlant")}>
          <Link href="/setup">{t("toSetup")}</Link>
        </EmptyState>
      </div>
    );
  }
  let state: ReactNode = null;
  if (facts.data && !run) {
    state = (
      <EmptyState title={t("toImport")}>
        {t("noImport")} <Link href="/import">{t("toImport")}</Link>
      </EmptyState>
    );
  } else if (run?.status === "calculating") {
    state = (
      <p role="status" className="m-0 text-sm">
        {t("calculating")}
      </p>
    );
  } else if (run?.status === "failed") {
    state = (
      <p role="alert" className="m-0 text-sm text-bad">
        {t("failed")} <Link href="/import">{t("toImport")}</Link>
      </p>
    );
  } else if (facts.data && rows.length === 0) {
    state = <p className="m-0 text-sm text-muted">{t("noFacts")}</p>;
  }

  const sortButton = (key: ColumnKey) => {
    const text = t(`col.${key}`);
    const term = TERM_OF[key];
    const active = sort.key === key;
    return (
      <span className="inline-flex items-center gap-2">
        {term ? <Term id={term}>{text}</Term> : text}
        <button
          type="button"
          aria-label={t("sortBy", { column: text })}
          aria-pressed={active}
          onClick={() => setSort({ key, desc: active ? !sort.desc : key !== "machine" })}
          className={`inline-flex h-6 w-6 cursor-pointer items-center justify-center border-0 bg-transparent p-0 text-xs ${active ? "text-accent" : "text-faint"}`}
        >
          {active ? (sort.desc ? "▼" : "▲") : "↕"}
        </button>
      </span>
    );
  };

  return (
    <div className="flex flex-col gap-4">
      {header}
      <p className="m-0 max-w-3xl text-sm">{t.rich("intro", termTags)}</p>
      {state}
      {found && run?.status === "ready" && (
        <ConstraintBanner
          detection={found}
          label={label}
          periodName={periodName(chosen)}
          loss={loss.data?.facts ?? []}
        />
      )}
      {rows.length > 0 && run?.status === "ready" && (
        <Panel label={t("tableLabel", { period: periodName(chosen) })}>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-line">
                  <th className={TH}>{sortButton("machine")}</th>
                  {COLUMNS.map(([key]) => (
                    <th key={key} className={TH}>
                      {sortButton(key)}
                    </th>
                  ))}
                  <th className={TH}>
                    <span className="sr-only">{t("details")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([code, row]) => (
                  <tr
                    key={code}
                    className={`border-b border-line ${open === code ? "bg-raised" : ""}`}
                  >
                    <td className={`${TD} ${code === bottleneck ? "pt-6" : ""}`}>
                      {code === bottleneck ? (
                        <ConstraintMarker tag={t("bottleneckTag")}>
                          <MachineName name={names.get(code) ?? code} code={code} />
                        </ConstraintMarker>
                      ) : (
                        <MachineName name={names.get(code) ?? code} code={code} />
                      )}
                    </td>
                    {COLUMNS.map(([key, , measure]) => (
                      <td key={key} className={`${TD} whitespace-nowrap`}>
                        <Cell
                          fact={row.get(measure)}
                          label={`${t(`col.${key}`)} · ${label(code)}`}
                        />
                      </td>
                    ))}
                    <td className={TD}>
                      <button
                        type="button"
                        onClick={() => setOpen(open === code ? null : code)}
                        aria-expanded={open === code}
                        aria-label={t("detailsOf", { machine: label(code) })}
                        className="cursor-pointer rounded-control border border-line-strong bg-transparent px-2 py-1 text-xs"
                      >
                        {t("details")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="m-0 mt-2 text-xs text-muted">
            {t("colHelp")} {t("confidenceNote")}
          </p>
        </Panel>
      )}
      {open && run?.status === "ready" && (
        <MachineDetail
          plant={plant ?? ""}
          code={open}
          name={label(open)}
          overview={byMachine.get(open)}
          period={chosen}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  );
}

/** Everything about one machine: timeline per day, task times, breakdowns, setup, missing data. */
function MachineDetail({
  plant,
  code,
  name,
  overview,
  period,
  onClose,
}: {
  plant: string;
  code: string;
  name: string;
  overview: Map<string, Fact> | undefined;
  period: Period | undefined;
  onClose: () => void;
}) {
  const t = useTranslations("machines");
  const tf = useTranslations("figure");
  const locale = useLocale();
  const details = useDetails();
  const periodQuery = period
    ? { period_kind: period.period_kind, period_start_at: period.period_start_at }
    : { period_kind: "all" as const };
  const days = useFacts(plant, { family: ["state"], resource_code: code, period_kind: "day" });
  const whole = useFacts(plant, {
    family: ["task_time", "down_reason"],
    resource_code: code,
  });
  const states = useFacts(plant, {
    family: ["state", "setup_share"],
    resource_code: code,
    ...periodQuery,
  });

  const inPeriod = (f: Fact) =>
    !period ||
    period.period_kind === "all" ||
    ((f.figure.period_start_at ?? "") >= period.period_start_at &&
      (f.figure.period_start_at ?? "") < period.period_end_at);
  const timeline = useMemo(() => {
    const out = new Map<string, Map<string, Fact>>();
    for (const f of days.data?.facts ?? []) {
      if (!inPeriod(f)) continue;
      const day = f.figure.period_start_at ?? "";
      const row = out.get(day) ?? new Map<string, Fact>();
      row.set(f.measure.replace(/_min$/, ""), f);
      out.set(day, row);
    }
    return [...out.entries()].sort(([a], [b]) => a.localeCompare(b));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days.data, period]);
  const tasks = (whole.data?.facts ?? []).filter((f) => f.family === "task_time");
  const operations = [...new Set(tasks.map((f) => f.operation ?? ""))].sort();
  const reasons = (whole.data?.facts ?? [])
    .filter((f) => f.family === "down_reason")
    .sort((a, b) => (valueOf(b) ?? 0) - (valueOf(a) ?? 0));
  const stateFacts = new Map((states.data?.facts ?? []).map((f) => [f.measure, f]));
  const missing = new Map<string, { what: string; reason: string; impact: string }>();
  for (const f of [
    ...(overview?.values() ?? []),
    ...stateFacts.values(),
    ...(whole.data?.facts ?? []),
  ]) {
    const v = f.figure.value;
    if (isMissing(v))
      missing.set(v.reason, { what: v.missing, reason: v.reason, impact: v.confidence_impact });
  }
  const day = (iso: string) =>
    new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "short" }).format(
      new Date(iso),
    );
  const shown = (key: string, measure: string) => `${t(key)} · ${name} · ${measure}`;

  return (
    <section aria-label={t("detailLabel", { machine: name })} className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="m-0 text-base font-medium" data-raw>
          {t("detailLabel", { machine: name })}
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="cursor-pointer rounded-control border border-line-strong bg-transparent px-2 py-1 text-xs"
        >
          {t("close")}
        </button>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        {(
          [
            ["kpiBusy", "utilisation_pct"],
            ["kpiOee", "oee_ratio"],
            ["kpiCapacity", "effective_capacity_h"],
          ] as const
        ).map(([key, measure]) => {
          const f = overview?.get(measure);
          return (
            <Panel key={key} label={t(key)}>
              <div className="flex flex-col gap-1">
                <MicroLabel>{name}</MicroLabel>
                {f ? (
                  <Figure
                    figure={f.figure as FigureLike}
                    label={`${t(key)} · ${name}`}
                    size="kpi"
                  />
                ) : (
                  <span className="text-faint">—</span>
                )}
              </div>
            </Panel>
          );
        })}
      </div>

      <Panel label={t("timelineLabel")}>
        <p className="m-0 mb-2 text-xs text-muted">{t("timelineHelp")}</p>
        <ul className="m-0 mb-2 flex list-none flex-wrap gap-3 p-0 text-xs">
          {TIMELINE.map(([s, colour]) => (
            <li key={s} className="flex items-center gap-1">
              <span
                aria-hidden="true"
                className={`inline-block h-3 w-3 border border-line ${colour}`}
              />
              {t(`state.${s}`)}
            </li>
          ))}
        </ul>
        {timeline.length === 0 ? (
          <p className="m-0 text-sm text-muted">{t("noTimeline")}</p>
        ) : (
          <div className="flex max-h-[28rem] flex-col gap-1 overflow-y-auto">
            {timeline.map(([start, row]) => {
              const shift = valueOf(row.get("shift")) ?? 0;
              if (shift <= 0) return null;
              return (
                <div key={start} className="flex items-center gap-2">
                  <span className="w-28 shrink-0 font-mono text-xs text-muted" data-raw>
                    {day(start)}
                  </span>
                  <div className="flex h-4 flex-1 border border-line">
                    {TIMELINE.map(([s, colour]) => {
                      const f = row.get(s);
                      const minutes = valueOf(f);
                      if (!f || !minutes) return null;
                      const text = t("timelineDay", { day: day(start), state: t(`state.${s}`) });
                      return (
                        <button
                          key={s}
                          type="button"
                          aria-label={text}
                          title={text}
                          onClick={() =>
                            details.show(
                              <HowCalculated figure={f.figure as FigureLike} label={text} />,
                            )
                          }
                          style={{ width: `${(minutes / shift) * 100}%` }}
                          className={`h-full cursor-pointer border-0 p-0 ${colour}`}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel label={t("tasksLabel")}>
          <p className="m-0 mb-2 text-xs text-muted">{t("tasksHelp")}</p>
          {operations.length === 0 ? (
            <p className="m-0 text-sm text-muted">{t("noTasks")}</p>
          ) : (
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-line">
                  <th className={TH}>{t("colOperation")}</th>
                  <th className={TH}>{t("colTypical")}</th>
                  <th className={TH}>{t("colSlow")}</th>
                </tr>
              </thead>
              <tbody>
                {operations.map((op) => {
                  const of = (m: string) =>
                    tasks.find((f) => f.operation === op && f.measure === m);
                  return (
                    <tr key={op} className="border-b border-line">
                      <td className={TD} data-raw>
                        {op}
                      </td>
                      <td className={TD}>
                        <Cell
                          fact={of("median_min_per_unit")}
                          label={`${t("colTypical")} · ${op}`}
                        />
                      </td>
                      <td className={TD}>
                        <Cell fact={of("p90_min_per_unit")} label={`${t("colSlow")} · ${op}`} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Panel>

        <div className="flex flex-col gap-4">
          <Panel label={t("downLabel")}>
            {reasons.length === 0 ? (
              <p className="m-0 text-sm text-muted">{t("noDown")}</p>
            ) : (
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-line">
                    <th className={TH}>{t("colReason")}</th>
                    <th className={TH}>{t("colMinutes")}</th>
                  </tr>
                </thead>
                <tbody>
                  {reasons.map((f) => (
                    <tr key={f.reason_code ?? ""} className="border-b border-line">
                      <td className={`${TD} font-mono`} data-raw>
                        {f.reason_code === "unknown" ? t("reasonUnknown") : f.reason_code}
                      </td>
                      <td className={TD}>
                        <Cell fact={f} label={`${t("colMinutes")} · ${f.reason_code ?? ""}`} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
          <Panel label={t("setupLabel")}>
            <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted">{t("setupTime")}</dt>
              <dd className="m-0">
                <Cell fact={stateFacts.get("setup_min")} label={shown("setupTime", "min")} />
              </dd>
              <dt className="text-muted">{t("setupShare")}</dt>
              <dd className="m-0">
                <Cell fact={stateFacts.get("setup_share_pct")} label={shown("setupShare", "%")} />
              </dd>
            </dl>
            <p className="m-0 mt-2 text-xs text-muted">{t("setupNoReason")}</p>
          </Panel>
          <Panel label={t("missingLabel")}>
            {missing.size === 0 ? (
              <p className="m-0 text-sm text-muted">{t("missingNone")}</p>
            ) : (
              <ul className="m-0 flex list-none flex-col gap-1 p-0 text-sm">
                {[...missing.values()].map((m) => (
                  <li key={m.reason} className="text-bad">
                    {t("missingItem", {
                      what: m.what,
                      reason: m.reason,
                      impact: tf(`level.${m.impact}`),
                    })}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>
    </section>
  );
}
