"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { ConstraintMarker, isMissing, MicroLabel, Panel, type FigureLike } from "@cip/ui";
import { useDetection } from "../ConstraintBanner";
import { useFacts, useFactPeriods, useMachineLabel, usePeriodName, type Fact } from "../diagnose";
import { EmptyState } from "../EmptyState";
import { Figure } from "../Figure";
import { PageHeader } from "../PageHeader";
import { PlantPicker, usePlant } from "../PlantPicker";
import { termTags } from "../terms";

const DAY_MS = 86_400_000;

/** The last month the data covers fully (at least 4 weeks), else the latest month. */
function lastMonth<
  T extends { period_kind: string; period_start_at: string; period_end_at: string },
>(periods: T[]): T | undefined {
  const months = periods.filter((p) => p.period_kind === "month");
  const full = months.filter(
    (p) => Date.parse(p.period_end_at) - Date.parse(p.period_start_at) >= 28 * DAY_MS,
  );
  return (full.length ? full : months).at(-1);
}

function pick(loss: Fact[], measure: string, cause: string): Fact | undefined {
  return loss.find((f) => f.measure === measure && f.reason_code === cause);
}

/** Overview: the answer in one sentence, how sure we are, the biggest causes, where to look. */
export function OverviewPage() {
  const t = useTranslations("overview");
  const tc = useTranslations("detection.loss.cause");
  const picker = usePlant();
  const { plant } = picker;
  const label = useMachineLabel(plant);
  const periodName = usePeriodName();
  const detection = useDetection(plant, { period_kind: "all" });
  const found = detection.data?.detections[0];
  const internal = found?.kind === "internal" && !!found.resource_code;
  const periods = useFactPeriods(plant);
  const month = lastMonth(periods.data ?? []);
  const monthLoss = useFacts(
    plant,
    { family: ["loss"], period_kind: "month", period_start_at: month?.period_start_at ?? "" },
    internal && !!month,
  );
  const wholeLoss = useFacts(plant, { family: ["loss"] }, internal);
  const busy = useFacts(plant, { family: ["utilisation"] }, !!found && !internal);

  const header = <PageHeader page="main" actions={<PlantPicker {...picker} />} />;
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
  } else if (detection.data && !found) {
    state = (
      <EmptyState title={t("noAnswerTitle")}>
        {t("noAnswer")} <Link href="/run">{t("toRun")}</Link>
      </EmptyState>
    );
  }

  const agree = found?.reasons.find((r) => r.code === "methods_agree");
  const sure = found ? t(`sure.${found.confidence}`) : "";
  const monthFacts = monthLoss.data?.facts ?? [];
  const money = pick(monthFacts, "lost_eur_cents", "total");
  const hours = pick(monthFacts, "lost_h", "total");
  const euros = money && money.figure.unit === "eur_cents" && !isMissing(money.figure.value);
  const causes = monthFacts
    .filter((f) => f.measure === "lost_h" && f.reason_code !== "total")
    .filter((f) => !isMissing(f.figure.value) && Number(f.figure.value) > 0)
    .sort((a, b) => Number(b.figure.value) - Number(a.figure.value))
    .slice(0, 3);
  const wholeFacts = wholeLoss.data?.facts ?? [];
  const wholeMoney = pick(wholeFacts, "lost_eur_cents", "total");
  const wholeHours = pick(wholeFacts, "lost_h", "total");
  const top = (busy.data?.facts ?? [])
    .filter((f) => f.measure === "utilisation_pct" && !isMissing(f.figure.value))
    .sort((a, b) => Number(b.figure.value) - Number(a.figure.value))[0];

  return (
    <div className="flex flex-col gap-4">
      {header}
      {state}
      {found && run?.status === "ready" && (
        <section
          aria-label={t("answerLabel")}
          className="flex flex-col gap-3 rounded-panel border border-line-strong bg-surface p-5"
        >
          <MicroLabel>{t("answerTag", { period: periodName(found) })}</MicroLabel>
          {internal && found.resource_code ? (
            <>
              <p className="m-0 flex flex-wrap items-baseline gap-x-2 gap-y-3 pt-5 text-xl">
                <ConstraintMarker tag={t("tag")}>
                  <span className="px-1 font-display" data-raw>
                    {label(found.resource_code)}
                  </span>
                </ConstraintMarker>
                <span>{t("limits")}</span>
              </p>
              {month && hours && (
                <p className="m-0 flex flex-wrap items-baseline gap-x-2 text-lg">
                  {euros && money ? (
                    <>
                      <span>{t("costAbout")}</span>
                      <Figure
                        figure={money.figure as FigureLike}
                        label={t("costLabel")}
                        size="inline"
                      />
                      <span data-raw>{t("inMonth", { month: periodName(month) })}</span>
                    </>
                  ) : (
                    <>
                      <span>{t("lostAbout")}</span>
                      <Figure figure={hours.figure as FigureLike} label={t("hoursLabel")} />
                      <span data-raw>{t("hoursInMonth", { month: periodName(month) })}</span>
                    </>
                  )}
                </p>
              )}
              {money && money.figure.unit === "eur_cents" && isMissing(money.figure.value) && (
                <p className="m-0 text-sm text-muted">
                  {t("noEuros")} <Link href="/import">{t("toImport")}</Link>
                </p>
              )}
            </>
          ) : (
            <>
              <p className="m-0 text-xl">{t(found.kind)}</p>
              {top && (
                <p className="m-0 flex flex-wrap items-baseline gap-x-2 text-sm">
                  <span data-raw>{t("busiest", { machine: label(top.resource_code) })}</span>
                  <Figure figure={top.figure as FigureLike} label={t("busyLabel")} />
                  <span>{t("busiestTail")}</span>
                </p>
              )}
            </>
          )}
          <p className="m-0 flex flex-wrap items-baseline gap-x-2 text-sm">
            <span className="font-medium">{sure}</span>
            {agree ? (
              <span data-raw>
                {t("because", {
                  count: Number(agree.values.count),
                  total: Number(agree.values.total),
                })}
              </span>
            ) : (
              <span>{t("becauseMarket")}</span>
            )}
            <span className="text-muted">{t("agreement")}</span>
            <Figure figure={found.agreement as FigureLike} label={t("agreement")} />
            <span className="text-muted">{t.rich("confidence", termTags)}</span>
            <span className="font-medium">{t(`level.${found.confidence}`)}</span>
          </p>
        </section>
      )}
      {internal && run?.status === "ready" && causes.length > 0 && month && (
        <Panel label={t("causesLabel", { month: periodName(month) })}>
          <ol className="m-0 flex flex-col gap-2 p-0 pl-5 text-sm">
            {causes.map((c) => {
              const cause = c.reason_code ?? "";
              const eur = pick(monthFacts, "lost_eur_cents", cause);
              return (
                <li key={cause}>
                  <span className="inline-flex flex-wrap items-baseline gap-x-2">
                    <span className="font-medium first-letter:uppercase">{tc(cause)}</span>
                    <Figure
                      figure={c.figure as FigureLike}
                      label={t("causeHours", { cause: tc(cause) })}
                    />
                    {eur && eur.figure.unit === "eur_cents" && !isMissing(eur.figure.value) && (
                      <Figure
                        figure={eur.figure as FigureLike}
                        label={t("causeEuros", { cause: tc(cause) })}
                      />
                    )}
                  </span>
                </li>
              );
            })}
          </ol>
          {wholeHours && (
            <p className="m-0 mt-3 flex flex-wrap items-baseline gap-x-2 text-sm text-muted">
              <span>{t("wholePeriod")}</span>
              <Figure figure={wholeHours.figure as FigureLike} label={t("hoursLabel")} />
              {wholeMoney && wholeMoney.figure.unit === "eur_cents" && (
                <Figure figure={wholeMoney.figure as FigureLike} label={t("costLabel")} />
              )}
            </p>
          )}
          <p className="m-0 mt-2 text-sm">
            <Link href="/loss">{t("toLoss")}</Link>
          </p>
        </Panel>
      )}
      {found && run?.status === "ready" && (
        <Panel label={t("evidenceLabel")}>
          <ul className="m-0 flex flex-col gap-1 p-0 pl-5 text-sm">
            <li>
              <Link href="/machines">
                {t(internal ? "evidence.machines" : "evidence.machinesNone")}
              </Link>
            </li>
            {internal && (
              <li>
                <Link href="/loss">{t("evidence.loss")}</Link>
              </li>
            )}
            <li>
              <Link href="/data">{t("evidence.data")}</Link>
            </li>
            <li>
              <Link href="/run">{t("evidence.run")}</Link>
            </li>
          </ul>
        </Panel>
      )}
    </div>
  );
}
