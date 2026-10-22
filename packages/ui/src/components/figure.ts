/** The API's Figure envelope (apps/api FigureOut): a number with its provenance. */
export interface MissingValue {
  missing: string;
  reason: string;
  confidence_impact: string;
}

export interface FigureLike {
  value: number | MissingValue;
  unit: string;
  formula_id: string;
  inputs: Record<string, unknown>;
  period_start_at?: string | null;
  period_end_at?: string | null;
  confidence: string;
}

export function isMissing(value: FigureLike["value"]): value is MissingValue {
  return typeof value === "object";
}

/**
 * Display formatting only (no calculation): cents shown as whole euros, hours with one
 * decimal, everything else as a localised number with its unit.
 */
export function formatFigure(figure: FigureLike, locale = "en"): string {
  const { value, unit } = figure;
  if (isMissing(value)) return "—";
  if (unit === "eur_cents") {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: "EUR",
      maximumFractionDigits: 0,
    }).format(value / 100);
  }
  if (unit === "h")
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)} h`;
  if (unit === "min_per_unit")
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)} min/unit`;
  if (unit === "weeks")
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)} wk`;
  if (unit === "score") return new Intl.NumberFormat(locale).format(value);
  if (unit === "ratio")
    return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }).format(
      value,
    );
  if (unit === "min")
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value)} min`;
  if (unit === "orders")
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)} orders`;
  if (unit === "pct")
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)}%`;
  return `${new Intl.NumberFormat(locale).format(value)} ${unit}`;
}
