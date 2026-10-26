"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { isMissing, MicroLabel, Panel, formatFigure, type FigureLike } from "@cip/ui";
import { useLocale } from "next-intl";
import { useDetails } from "../Details";
import { useDetection } from "../ConstraintBanner";
import { useFacts, useMachineLabel, usePeriodName, valueOf, type Fact } from "../diagnose";
import { EmptyState } from "../EmptyState";
import { Figure, HowCalculated } from "../Figure";
import { PageHeader } from "../PageHeader";
import { PlantPicker, usePlant } from "../PlantPicker";
import { termTags } from "../terms";

const CAUSES = ["breakdowns", "setup", "starved", "blocked", "breaks", "maintenance", "scrap"];
/** Grey tones per cause; the largest cause is drawn in the accent colour instead. */
// breakdowns, setup, starved, blocked, breaks, maintenance, scrap: neighbours differ clearly
const GREYS = [
  "bg-line-strong",
  "bg-faint",
  "bg-idle",
  "bg-line",
  "bg-text",
  "bg-raised",
  "bg-muted",
];

const TH =
  "px-3 py-2 text-left text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted";
const TD = "px-3 py-2 align-top whitespace-nowrap";

type Kind = "month" | "week";

/** Sentence-case a cause name for a label ("setups" → "Setups"). Display only. */
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
type Show = "eur" | "h";

/** Loss: the hours and euros the bottleneck lost per month or week, by cause. */
export function LossPage() {
  const t = useTranslations("loss");
  const tc = useTranslations("detection.loss.cause");
  const locale = useLocale();
  const details = useDetails();
  const picker = usePlant();
  const { plant } = picker;
  const label = useMachineLabel(plant);
  const periodName = usePeriodName();
  const [kind, setKind] = useState<Kind>("month");
  const [showPref, setShow] = useState<Show>("eur");

  const detection = useDetection(plant, { period_kind: "all" });
  const found = detection.data?.detections[0];
  const internal = found?.kind === "internal" && !!found.resource_code;
  const whole = useFacts(plant, { family: ["loss"] }, internal);
  const periods = useFacts(plant, { family: ["loss"], period_kind: kind }, !!found);
  const periodDetections = useDetection(plant, { period_kind: kind });

  const wholeFacts = whole.data?.facts ?? [];
  const totalEur = wholeFacts.find(
    (f) => f.measure === "lost_eur_cents" && f.reason_code === "total",
  );
  // Euros only when the role sees euros and prices exist; otherwise hours.
  const eurOk =
    !!totalEur && totalEur.figure.unit === "eur_cents" && !isMissing(totalEur.figure.value);
  const show: Show = eurOk ? showPref : "h";
  const measure = show === "eur" ? "lost_eur_cents" : "lost_h";

  const wholeHours = (cause: string) =>
    valueOf(wholeFacts.find((f) => f.measure === "lost_h" && f.reason_code === cause)) ?? 0;
  const biggest = [...CAUSES].sort((a, b) => wholeHours(b) - wholeHours(a))[0] ?? "setup";
  const colour = (cause: string) =>
    cause === biggest ? "bg-accent" : (GREYS[CAUSES.indexOf(cause)] ?? "bg-line-strong");

  // One row per period: its facts by cause.
  const rows = new Map<string, Map<string, Fact>>();
  for (const f of periods.data?.facts ?? []) {
    if (f.measure !== measure || !f.figure.period_start_at) continue;
    const row = rows.get(f.figure.period_start_at) ?? new Map<string, Fact>();
    row.set(f.reason_code ?? "", f);
    rows.set(f.figure.period_start_at, row);
  }
  const allPeriods = (periodDetections.data?.detections ?? []).map((d) => ({
    period_kind: d.period_kind,
    period_start_at: d.period_start_at,
    bottleneck: d.kind === "internal" ? d.resource_code : null,
  }));
  const peak = Math.max(1, ...[...rows.values()].map((r) => valueOf(r.get("total")) ?? 0));

  const header = (
    <PageHeader
      page="loss"
      headline={
        internal && found?.resource_code && wholeFacts.length > 0 ? (
          <span data-raw>
            {t("headline", { cause: tc(biggest), machine: label(found.resource_code) })}
          </span>
        ) : undefined
      }
      actions={<PlantPicker {...picker} />}
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
  const run = detection.data?.run;
  let state: ReactNode = null;
  if (detection.data && !run) {
    state = (
      <EmptyState title={t("noImportTitle")}>
        {t("noImport")} <Link href="/import">{t("toImport")}</Link>
      </EmptyState>
    );
  } else if (run?.status === "calculating" && !run.finished_at) {
    state = (
      <p role="status" className="m-0 text-sm">
        {t("calculating")}
      </p>
    );
  } else if (run?.status === "failed" && !run.finished_at) {
    state = (
      <p role="alert" className="m-0 text-sm text-bad">
        {t("failed")} <Link href="/import">{t("toImport")}</Link>
      </p>
    );
  } else if (found && !internal) {
    state = (
      <EmptyState title={t("noBottleneckTitle")}>
        {t(`noBottleneck.${found.kind}`)} <Link href="/main">{t("toOverview")}</Link>
      </EmptyState>
    );
  }

  const toggle = (
    <div className="flex flex-wrap items-center gap-4 text-sm">
      <div role="group" aria-label={t("periodLabel")} className="flex gap-1">
        {(["month", "week"] as const).map((k) => (
          <button
            key={k}
            type="button"
            aria-pressed={kind === k}
            onClick={() => setKind(k)}
            className={`cursor-pointer rounded-control border px-2 py-1 text-xs ${kind === k ? "border-accent text-accent" : "border-line-strong bg-transparent text-muted"}`}
          >
            {t(`by.${k}`)}
          </button>
        ))}
      </div>
      {eurOk && (
        <div role="group" aria-label={t("showLabel")} className="flex gap-1">
          {(["eur", "h"] as const).map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={show === s}
              onClick={() => setShow(s)}
              className={`cursor-pointer rounded-control border px-2 py-1 text-xs ${show === s ? "border-accent text-accent" : "border-line-strong bg-transparent text-muted"}`}
            >
              {t(`show.${s}`)}
            </button>
          ))}
        </div>
      )}
    </div>
  );

  const ordered = allPeriods.filter((p) => p.period_kind === kind);
  return (
    <div className="flex flex-col gap-4">
      {header}
      <p className="m-0 max-w-3xl text-sm">{t.rich("intro", termTags)}</p>
      {state}
      {internal && run?.finished_at && (
        <>
          {toggle}
          {!eurOk && totalEur && totalEur.figure.unit === "eur_cents" && (
            <p className="m-0 text-sm text-muted">
              {t("noEuros")} <Link href="/import">{t("toImport")}</Link>
            </p>
          )}
          <Panel label={t("chartLabel", { unit: t(`unit.${show}`), by: t(`by.${kind}`) })}>
            <ul
              aria-label={t("legend")}
              className="m-0 mb-3 flex list-none flex-wrap gap-3 p-0 text-xs"
            >
              {CAUSES.map((c) => (
                <li key={c} className="flex items-center gap-1">
                  <span aria-hidden="true" className={`inline-block size-3 ${colour(c)}`} />
                  <span className={c === biggest ? "font-medium" : "text-muted"}>
                    {cap(tc(c))}
                    {c === biggest ? ` · ${t("biggest")}` : ""}
                  </span>
                </li>
              ))}
            </ul>
            <div className="flex items-end gap-2 overflow-x-auto pb-1" style={{ height: 220 }}>
              {ordered.map((p) => {
                const row = rows.get(p.period_start_at);
                const name = periodName(p);
                if (!row || !p.bottleneck) {
                  return (
                    <div
                      key={p.period_start_at}
                      className="flex w-14 shrink-0 flex-col items-center justify-end gap-1 self-stretch"
                    >
                      <span className="text-center text-micro text-muted">{t("none")}</span>
                      <span className="text-center text-micro text-muted" data-raw>
                        {name}
                      </span>
                    </div>
                  );
                }
                return (
                  <div
                    key={p.period_start_at}
                    className="flex w-14 shrink-0 flex-col items-center justify-end gap-1 self-stretch"
                  >
                    <div className="flex w-6 flex-col-reverse" style={{ height: 170 }}>
                      {CAUSES.map((c) => {
                        const f = row.get(c);
                        const v = valueOf(f);
                        if (!f || !v) return null;
                        return (
                          <button
                            key={c}
                            type="button"
                            aria-label={t("segment", {
                              period: name,
                              cause: tc(c),
                              amount: formatFigure(f.figure as FigureLike, locale),
                            })}
                            onClick={() =>
                              details.show(
                                <HowCalculated
                                  figure={f.figure as FigureLike}
                                  label={`${cap(tc(c))} · ${name}`}
                                />,
                              )
                            }
                            className={`block w-full cursor-pointer border-0 p-0 ${colour(c)}`}
                            style={{ height: `${(170 * v) / peak}px` }}
                          />
                        );
                      })}
                    </div>
                    <span className="text-center text-micro text-muted" data-raw>
                      {name}
                    </span>
                  </div>
                );
              })}
            </div>
          </Panel>
          <Panel label={t("tableLabel", { unit: t(`unit.${show}`) })}>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-line">
                    <th className={TH}>{t("colPeriod")}</th>
                    {CAUSES.map((c) => (
                      <th key={c} className={`${TH} ${c === biggest ? "text-text" : ""}`}>
                        {tc(c)}
                      </th>
                    ))}
                    <th className={TH}>{t("colTotal")}</th>
                  </tr>
                </thead>
                <tbody>
                  {ordered.map((p) => {
                    const row = rows.get(p.period_start_at);
                    const name = periodName(p);
                    return (
                      <tr key={p.period_start_at} className="border-b border-line">
                        <td className={TD}>
                          <span data-raw>{name}</span>
                          {p.bottleneck && (
                            <span className="block font-mono text-xs text-muted" data-raw>
                              {p.bottleneck}
                            </span>
                          )}
                        </td>
                        {row ? (
                          [...CAUSES, "total"].map((c) => {
                            const f = row.get(c);
                            return (
                              <td key={c} className={`${TD} ${c === "total" ? "font-medium" : ""}`}>
                                {f ? (
                                  <Figure
                                    figure={f.figure as FigureLike}
                                    label={`${c === "total" ? t("colTotal") : cap(tc(c))} · ${name}`}
                                  />
                                ) : (
                                  <span className="text-faint">—</span>
                                )}
                              </td>
                            );
                          })
                        ) : (
                          <td className={`${TD} text-muted`} colSpan={CAUSES.length + 1}>
                            {t("noneRow")}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="m-0 mt-2 text-xs text-muted">{t("tableHelp")}</p>
          </Panel>
          <MicroLabel>{t("next")}</MicroLabel>
          <p className="m-0 -mt-2 text-sm">
            <Link href="/machines">{t("toMachines")}</Link>
          </p>
        </>
      )}
    </div>
  );
}
