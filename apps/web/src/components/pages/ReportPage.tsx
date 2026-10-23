"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { Button, MicroLabel, type FigureLike } from "@cip/ui";
import { api } from "@/lib/api/client";
import { useDetection } from "../ConstraintBanner";
import { useFacts, useFactPeriods, useMachineLabel, usePeriodName } from "../diagnose";
import { EmptyState } from "../EmptyState";
import { Count, Figure, useFormulaText, useInputLines } from "../Figure";
import { PageHeader } from "../PageHeader";
import { PlantPicker, usePlant } from "../PlantPicker";
import { TechnicalDetails } from "../Problems";
import { buildReport, type Line, type Report, type Translate } from "../report/model";

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

function LineView({ line }: { line: Line }) {
  const t = useTranslations("report");
  return (
    <p className="m-0 flex flex-wrap items-baseline gap-x-2 gap-y-1">
      {line.map((s, i) => {
        if ("text" in s) {
          return (
            <span key={i} data-raw>
              {s.text}
            </span>
          );
        }
        if ("figure" in s) {
          return (
            <span key={i} className="inline-flex items-baseline gap-1.5">
              <Figure figure={s.figure} label={s.label} />
              <a
                href={`#source-${s.ref}`}
                aria-label={t("sourceLink", { n: s.ref })}
                className="inline-flex min-h-6 min-w-6 items-center justify-center text-xs text-muted"
                data-raw
              >
                [{s.ref}]
              </a>
            </span>
          );
        }
        return <Count key={i} value={s.count} label={s.label} source={s.source} />;
      })}
    </p>
  );
}

function ReportView({ report }: { report: Report }) {
  const t = useTranslations("report");
  return (
    <article
      aria-label={report.title}
      className="flex flex-col gap-5 rounded-panel border border-line-strong bg-surface p-5"
    >
      <header className="flex flex-col gap-1">
        <h2 className="m-0 font-display text-xl" data-raw>
          {report.plant}
        </h2>
        <p className="m-0 text-sm text-muted" data-raw>
          {report.period}
        </p>
        <p className="m-0 text-xs text-muted" data-raw>
          {report.made}
        </p>
      </header>
      {report.sections.map((section) => (
        <section
          key={section.key}
          aria-label={section.heading}
          className="flex flex-col gap-2 border-t border-line pt-4 text-sm"
        >
          <h3 className="m-0">
            <MicroLabel>{section.heading}</MicroLabel>
          </h3>
          {section.lines.map((line, i) => (
            <LineView key={i} line={line} />
          ))}
        </section>
      ))}
      <section
        aria-label={t("sources")}
        className="flex flex-col gap-2 border-t border-line pt-4 text-sm"
      >
        <h3 className="m-0">
          <MicroLabel>{t("sources")}</MicroLabel>
        </h3>
        <p className="m-0 text-muted">{t("sourcesIntro")}</p>
        <ol className="m-0 flex list-none flex-col gap-3 p-0">
          {report.sources.map((s) => (
            <li key={s.ref} id={`source-${s.ref}`} className="flex flex-col gap-0.5">
              <span className="flex flex-wrap items-baseline gap-x-2 font-medium">
                <span data-raw>
                  [{s.ref}] {s.label}:
                </span>
                <Figure figure={s.figure} label={s.label} />
              </span>
              {s.formula && (
                <span className="text-muted" data-raw>
                  {t("sourceFormula")}: {s.formula}
                </span>
              )}
              {s.inputs.length > 0 && (
                <span className="text-muted" data-raw>
                  {t("sourceInputs")}: {s.inputs.join("; ")}
                </span>
              )}
              <span className="text-muted" data-raw>
                {t("sourcePeriod")}: {s.period}. {t("sourceConfidence")}: {s.confidence}.
              </span>
            </li>
          ))}
        </ol>
      </section>
    </article>
  );
}

/** Results report: what limits output, what it cost, how sure we are, the data, the method. */
export function ReportPage() {
  const t = useTranslations("report");
  const to = useTranslations("overview");
  const root = useTranslations();
  const locale = useLocale();
  const picker = usePlant();
  const { plant, plants } = picker;
  const label = useMachineLabel(plant);
  const periodName = usePeriodName();
  const formulaText = useFormulaText();
  const inputLines = useInputLines();
  const [madeAt] = useState(() => new Date());
  const [pdf, setPdf] = useState<{ busy: boolean; saved?: string; error?: string }>({
    busy: false,
  });

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
  const quality = useQuery({
    queryKey: ["data-quality", plant],
    enabled: plant !== null,
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/data-quality", {
          params: { path: { plant_code: plant ?? "" } },
        })
      ).data ?? null,
  });

  const header = (
    <PageHeader page="report" headline={t("headline")} actions={<PlantPicker {...picker} />} />
  );
  if (plants && plants.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        {header}
        <EmptyState title={to("noPlant")}>
          <Link href="/setup">{to("toSetup")}</Link>
        </EmptyState>
      </div>
    );
  }

  const run = detection.data?.run;
  let state: ReactNode = null;
  if (detection.isError || quality.isError) {
    state = (
      <p role="alert" className="m-0 text-sm text-bad">
        {t("loadFailed")}
      </p>
    );
  } else if (detection.data && !run) {
    state = (
      <EmptyState title={to("noImportTitle")}>
        {to("noImport")} <Link href="/import">{to("toImport")}</Link>
      </EmptyState>
    );
  } else if (run?.status === "calculating") {
    state = (
      <p role="status" className="m-0 text-sm">
        {to("calculating")}
      </p>
    );
  } else if (run?.status === "failed") {
    state = (
      <p role="alert" className="m-0 text-sm text-bad">
        {to("failed")} <Link href="/import">{to("toImport")}</Link>
      </p>
    );
  } else if (detection.data && !found) {
    state = (
      <EmptyState title={to("noAnswerTitle")}>
        {to("noAnswer")} <Link href="/run">{to("toRun")}</Link>
      </EmptyState>
    );
  }

  const loading =
    !found ||
    quality.isPending ||
    periods.isPending ||
    (internal && (wholeLoss.isPending || (!!month && monthLoss.isPending))) ||
    (!internal && busy.isPending);
  const plantName = plants?.find((p) => p.plant_code === plant)?.name ?? plant ?? "";
  const report =
    found && run?.status === "ready" && !loading && plant
      ? buildReport({
          plantCode: plant,
          plantName,
          detection: found,
          ...(month ? { month } : {}),
          monthLoss: monthLoss.data?.facts ?? [],
          wholeLoss: wholeLoss.data?.facts ?? [],
          utilisation: busy.data?.facts ?? [],
          quality: quality.data ?? null,
          label,
          periodName,
          t: ((key, values) => root(key, values)) as Translate,
          locale,
          formulaText: (f: FigureLike) => formulaText(f),
          inputLines: (f: FigureLike) => inputLines(f),
          madeAt,
        })
      : null;

  const download = async (r: Report) => {
    setPdf({ busy: true });
    try {
      const { reportPdf } = await import("../report/pdf");
      const bytes = await reportPdf(r, {
        sources: t("sources"),
        sourcesIntro: t("sourcesIntro"),
        formula: t("sourceFormula"),
        inputs: t("sourceInputs"),
        period: t("sourcePeriod"),
        confidence: t("sourceConfidence"),
        formulaId: t("sourceFormulaId"),
        page: (n, total) => t("page", { n, total }),
      });
      const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = r.fileName;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
      setPdf({ busy: false, saved: r.fileName });
    } catch (e) {
      setPdf({ busy: false, error: String(e) });
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {header}
      {state}
      {!state && !report && (
        <p role="status" className="m-0 text-sm">
          {t("preparing")}
        </p>
      )}
      {report && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary" isDisabled={pdf.busy} onPress={() => void download(report)}>
              {pdf.busy ? t("downloading") : t("download")}
            </Button>
            {pdf.saved && (
              <span role="status" className="text-sm text-muted" data-raw>
                {t("downloaded", { file: pdf.saved })}
              </span>
            )}
          </div>
          {pdf.error && (
            <div role="alert" className="flex flex-col gap-1 text-sm text-bad">
              <p className="m-0">{t("pdfFailed")}</p>
              <TechnicalDetails lines={[pdf.error]} />
            </div>
          )}
          <ReportView report={report} />
          <p className="m-0 text-sm">
            <Link href="/main">{t("toOverview")}</Link>
          </p>
        </>
      )}
    </div>
  );
}
