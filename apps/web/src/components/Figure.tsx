"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { formatFigure, isMissing, MicroLabel, type FigureLike, type MissingValue } from "@cip/ui";
import { api } from "@/lib/api/client";
import { useDetails } from "./Details";
import { TechnicalDetails } from "./Problems";
import { termTags } from "./terms";

/** Where a plain (non-figure) input comes from, so every input opens its own source. */
const INPUT_SOURCE: Record<string, string> = {
  rows: "/import",
  valid_rows: "/import",
  rejected_rows: "/import",
  gaps_high: "/data",
  gaps_medium: "/data",
  gaps_low: "/data",
  gaps_none: "/data",
  first_event_at: "/data",
  last_event_at: "/data",
  sales_price_eur_cents: "/setup",
  truly_variable_cost_eur_cents: "/setup",
  planned_production_min: "/calendar",
  unplanned_stop_min: "/data",
};

const UNIT_SUFFIX: [string, string][] = [
  ["_eur_cents", "€"],
  ["_min_per_unit", "min/unit"],
  ["_min", "min"],
  ["_h", "h"],
  ["_pct", "%"],
  ["_units", "units"],
  ["_at", ""],
];

const isFigure = (v: unknown): v is FigureLike =>
  typeof v === "object" && v !== null && "formula_id" in v;
const isMissingInput = (v: unknown): v is MissingValue =>
  typeof v === "object" && v !== null && "missing" in v;

/** "truly_variable_cost_eur_cents" → ["truly variable cost", "€"]. Display only. */
function inputName(key: string): [string, string] {
  const [suffix, unit] = UNIT_SUFFIX.find(([s]) => key.endsWith(s)) ?? ["", ""];
  return [key.slice(0, key.length - suffix.length).replaceAll("_", " "), unit];
}

function inputValue(key: string, value: unknown, locale: string): string {
  if (typeof value === "number") {
    if (key.endsWith("_eur_cents")) {
      return new Intl.NumberFormat(locale, { style: "currency", currency: "EUR" }).format(
        value / 100,
      );
    }
    return new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value);
  }
  if (typeof value === "string" && key.endsWith("_at")) {
    return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(value));
  }
  return String(value);
}

/** Plain formula texts from the engine (GET /meta), for formulas without a plain message. */
function useFormulaTexts(): Map<string, string> {
  const query = useQuery({
    queryKey: ["meta"],
    queryFn: async () => (await api.GET("/meta")).data ?? null,
    staleTime: Infinity,
  });
  const formulas = (query.data as { formulas?: { formula_id: string; text: string }[] } | null)
    ?.formulas;
  return new Map((formulas ?? []).map((f) => [f.formula_id, f.text]));
}

/** The "how is this calculated" panel: value, formula in plain words, inputs, period, confidence. */
export function HowCalculated({ figure, label }: { figure: FigureLike; label: string }) {
  const t = useTranslations("figure");
  const locale = useLocale();
  const details = useDetails();
  const engineTexts = useFormulaTexts();
  const name = figure.formula_id.replace(/_v\d+$/, "");
  const formula = t.has(`formulas.${name}`)
    ? t(`formulas.${name}`)
    : (engineTexts.get(figure.formula_id) ?? "");
  const missing = isMissing(figure.value) ? figure.value : null;
  const date = (iso: string) =>
    new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(iso));
  const open = (input: FigureLike, inputLabel: string) =>
    details.show(<HowCalculated figure={input} label={inputLabel} />);

  const rows: ReactNode[] = Object.entries(figure.inputs).map(([key, value]) => {
    const [plain, unit] = inputName(key);
    const shownLabel = unit ? `${plain} (${unit})` : plain;
    if (isFigure(value)) {
      return (
        <li key={key}>
          <button
            type="button"
            onClick={() => open(value, plain)}
            aria-label={t("openInput", { label: plain })}
            className="cursor-pointer border-0 bg-transparent p-0 text-left text-accent underline decoration-dotted underline-offset-4"
          >
            {shownLabel}: {isMissing(value.value) ? t("missing") : formatFigure(value, locale)}
          </button>
        </li>
      );
    }
    if (isMissingInput(value)) {
      return (
        <li key={key} className="text-bad">
          {t("missingInput", {
            what: plain,
            reason: value.reason,
            impact: t(`level.${value.confidence_impact}`),
          })}
        </li>
      );
    }
    const source = INPUT_SOURCE[key];
    return (
      <li key={key}>
        {shownLabel}: <span className="font-mono">{inputValue(key, value, locale)}</span>
        {source && (
          <>
            {" · "}
            <Link href={source}>{t("seeSource")}</Link>
          </>
        )}
      </li>
    );
  });

  return (
    <section aria-label={t("title")} className="flex flex-col gap-3 p-3 text-sm">
      <button
        type="button"
        onClick={details.clear}
        className="cursor-pointer self-start border-0 bg-transparent p-0 text-xs text-accent"
      >
        ← {t("back")}
      </button>
      <div>
        <MicroLabel>{label}</MicroLabel>
        <p className="m-0 mt-1 font-display text-2xl font-bold leading-none">
          {missing ? t("missing") : formatFigure(figure, locale)}
        </p>
        <p className="m-0 mt-1 text-xs text-muted">
          {t.has(`units.${figure.unit}`) ? t(`units.${figure.unit}`) : figure.unit}
        </p>
      </div>
      {missing && (
        <p className="m-0 text-bad">
          {t("missingInput", {
            what: missing.missing,
            reason: missing.reason,
            impact: t(`level.${missing.confidence_impact}`),
          })}
        </p>
      )}
      <div>
        <MicroLabel>{t("formula")}</MicroLabel>
        <p className="m-0 mt-1">{formula}</p>
      </div>
      {rows.length > 0 && (
        <div>
          <MicroLabel>{t("inputs")}</MicroLabel>
          <ul className="m-0 mt-1 flex list-none flex-col gap-1 p-0">{rows}</ul>
        </div>
      )}
      <div>
        <MicroLabel>{t("period")}</MicroLabel>
        <p className="m-0 mt-1">
          {figure.period_start_at && figure.period_end_at
            ? `${date(figure.period_start_at)} → ${date(figure.period_end_at)}`
            : t("periodAll")}
        </p>
      </div>
      <div>
        <MicroLabel>{t.rich("confidence", termTags)}</MicroLabel>
        <p className="m-0 mt-1">
          {t.has(`level.${figure.confidence}`)
            ? t(`level.${figure.confidence}`)
            : figure.confidence}
        </p>
      </div>
      <p className="m-0 text-xs text-muted">{t("calculatedBy")}</p>
      <TechnicalDetails lines={[t("formulaId", { id: figure.formula_id })]} />
    </section>
  );
}

/**
 * An engine number. Every number on screen is one of these: clicking it (or Enter) opens how it
 * is calculated in the Details panel. `size="kpi"` for headline numbers, inline otherwise.
 */
export function Figure({
  figure,
  label,
  size = "inline",
}: {
  figure: FigureLike;
  label: string;
  size?: "kpi" | "inline";
}) {
  const t = useTranslations("figure");
  const locale = useLocale();
  const details = useDetails();
  const missing = isMissing(figure.value);
  const text = missing ? t("missing") : formatFigure(figure, locale);
  return (
    <button
      type="button"
      data-figure={figure.formula_id}
      aria-label={`${text}. ${t("open", { label })}`}
      onClick={() => details.show(<HowCalculated figure={figure} label={label} />)}
      className={`cursor-pointer self-start border-0 bg-transparent p-0 text-left underline decoration-line-strong decoration-dotted underline-offset-4 hover:decoration-accent ${
        size === "kpi"
          ? "font-display text-2xl font-bold leading-none"
          : "font-mono text-[length:inherit]"
      } ${missing ? "text-muted" : "text-text"}`}
    >
      {text}
    </button>
  );
}

/** Where a count comes from: what was counted, and the page that shows it. */
export interface CountSource {
  /** Plain words, e.g. "orders.csv in the import of 22 Oct 2026". */
  what: string;
  href?: string;
  page?: string;
}

function CountPanel({
  value,
  label,
  source,
  kind,
}: {
  value: string;
  label: string;
  source: CountSource;
  kind: "count" | "given";
}) {
  const t = useTranslations("figure");
  const details = useDetails();
  return (
    <section aria-label={t("countTitle")} className="flex flex-col gap-3 p-3 text-sm">
      <button
        type="button"
        onClick={details.clear}
        className="cursor-pointer self-start border-0 bg-transparent p-0 text-xs text-accent"
      >
        ← {t("back")}
      </button>
      <div>
        <MicroLabel>{label}</MicroLabel>
        <p className="m-0 mt-1 font-display text-2xl font-bold leading-none">{value}</p>
      </div>
      <p className="m-0">{kind === "count" ? t("isCount") : t("isGiven")}</p>
      <p className="m-0">{t("countedFrom", { source: source.what })}</p>
      {source.href && source.page && (
        <Link href={source.href}>{t("seeIt", { page: source.page })}</Link>
      )}
    </section>
  );
}

/**
 * A plain count (rows, files, machines): no formula, but it still opens where it comes from.
 * Every number on screen is a Figure or a Count.
 */
export function Count({
  value,
  label,
  source,
  size = "inline",
  kind = "count",
  format,
  children,
}: {
  value: number;
  label: string;
  source: CountSource;
  size?: "kpi" | "inline";
  /** "given": a value from the client's own data (price, minutes), not a count. */
  kind?: "count" | "given";
  /** Display formatting, e.g. euros from cents. Default: localised number. */
  format?: (value: number) => string;
  /** Optional custom rendering of the value (e.g. "8 / 8"). */
  children?: ReactNode;
}) {
  const t = useTranslations("figure");
  const locale = useLocale();
  const details = useDetails();
  const text = format ? format(value) : new Intl.NumberFormat(locale).format(value);
  return (
    <button
      type="button"
      data-count={kind}
      aria-label={`${text}. ${t("open", { label })}`}
      onClick={() =>
        details.show(<CountPanel value={text} label={label} source={source} kind={kind} />)
      }
      className={`cursor-pointer self-start border-0 bg-transparent p-0 text-left text-text underline decoration-line-strong decoration-dotted underline-offset-4 hover:decoration-accent ${
        size === "kpi"
          ? "font-display text-2xl font-bold leading-none"
          : "font-mono text-[length:inherit]"
      }`}
    >
      {children ?? text}
    </button>
  );
}
