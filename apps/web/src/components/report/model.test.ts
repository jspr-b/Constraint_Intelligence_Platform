import { createTranslator } from "next-intl";
import { describe, expect, it } from "vitest";
import en from "../../../messages/en.json";
import { buildReport, lineText, type ReportInput, type Translate } from "./model";
import { reportPdf } from "./pdf";

const tr = createTranslator({
  locale: "en",
  messages: en,
  onError: (e) => {
    throw e;
  },
});
const t = ((key, values) => tr(key as never, values as never)) as Translate;

const fig = (value: number, unit: string, formula_id: string) => ({
  value,
  unit,
  formula_id,
  inputs: { lost_h: 1 },
  period_start_at: "2026-07-01T12:00:00Z",
  period_end_at: "2026-10-15T12:00:00Z",
  confidence: "high",
});

const fact = (measure: string, reason: string, value: number, unit: string) => ({
  family: "loss" as const,
  resource_code: "PNT-01",
  measure,
  operation: null,
  reason_code: reason,
  period_kind: "all" as const,
  figure: fig(value, unit, `${measure}_v1`),
});

const detection = {
  period_kind: "all" as const,
  period_start_at: "2026-07-01T12:00:00Z",
  period_end_at: "2026-10-15T12:00:00Z",
  resource_code: "PNT-01",
  kind: "internal" as const,
  confidence: "high" as const,
  agreement: fig(1, "ratio", "method_agreement_v1"),
  reasons: [{ code: "methods_agree", values: { count: 4, total: 4, machine: "PNT-01" } }],
  methods: (["utilisation", "queue", "active_period", "starved_blocked"] as const).map((m) => ({
    method: m,
    resource_code: "PNT-01",
    top_code: "PNT-01",
    evidence: fig(91, "pct", `${m}_v1`),
  })),
};

const quality = {
  plant_code: "PLANT-A",
  import_id: null,
  imported_at: "2026-10-22T08:00:00Z",
  score: fig(88, "score", "data_quality_score_v1"),
  rows: fig(1000, "rows", "record_count_v1"),
  files: [{ file: "orders.csv", rows: 120, rejected: 2, reasons: {}, examples: [] }],
  files_required: 8,
  files_missing: [],
  gaps: [
    {
      code: "no_shift_calendar",
      description: "No shift calendar was supplied.",
      confidence_impact: "medium",
      fix: "Add the capacity calendar.",
      resource_code: null,
      count: 1,
    },
  ],
  event_period_weeks: fig(15, "weeks", "event_period_weeks_v1"),
  event_period_start_at: "2026-07-01T12:00:00Z",
  event_period_end_at: "2026-10-15T12:00:00Z",
};

function input(over: Partial<ReportInput> = {}): ReportInput {
  return {
    plantCode: "PLANT-A",
    plantName: "Plant A (synthetic)",
    detection,
    month: {
      period_kind: "month",
      period_start_at: "2026-09-01T12:00:00Z",
      period_end_at: "2026-10-01T12:00:00Z",
    },
    monthLoss: [
      fact("lost_eur_cents", "total", 16_904_100, "eur_cents"),
      fact("lost_h", "total", 81.5, "h"),
    ],
    wholeLoss: [
      fact("lost_h", "total", 231.1, "h"),
      fact("lost_eur_cents", "total", 43_344_100, "eur_cents"),
      fact("lost_h", "setup", 120, "h"),
      fact("lost_eur_cents", "setup", 20_000_000, "eur_cents"),
      fact("lost_h", "breaks", 80, "h"),
      fact("lost_h", "blocked", 0, "h"),
    ],
    utilisation: [],
    quality,
    label: (code) => `Paint line (${code})`,
    periodName: () => "September 2026",
    t,
    locale: "en",
    formulaText: () => "A formula in plain words.",
    inputLines: () => ["lost hours (h): 1"],
    madeAt: new Date("2026-10-23T10:00:00Z"),
    ...over,
  };
}

const allText = (r: ReturnType<typeof buildReport>) =>
  r.sections.flatMap((s) => [s.heading, ...s.lines.map(lineText)]).join("\n");

describe("results report model", () => {
  it("says what limits output, what it cost, how sure, the data and the method", () => {
    const r = buildReport(input());
    expect(r.sections.map((s) => s.key)).toEqual(["answer", "cost", "sure", "data", "method"]);
    const text = allText(r);
    expect(text).toContain("Paint line (PNT-01) limits your output.");
    expect(text).toContain("€169,041 [1]");
    expect(text).toContain("Setups:");
    expect(text).not.toContain("Blocked:"); // zero causes are left out
    expect(text).toContain("4 of 4 independent checks");
    expect(text).toContain(
      "Gap: No shift calendar was supplied. Effect on confidence: medium. To fix: Add the capacity calendar.",
    );
    expect(r.fileName).toBe("results-report_PLANT-A_2026-07-01_to_2026-10-15.pdf");
  });

  it("gives every number one numbered source, in order", () => {
    const r = buildReport(input());
    expect(r.sources.map((s) => s.ref)).toEqual(r.sources.map((_, i) => i + 1));
    const refs = r.sections.flatMap((s) =>
      s.lines.flatMap((l) => l.flatMap((seg) => ("ref" in seg ? [seg.ref] : []))),
    );
    expect(new Set(refs)).toEqual(new Set(r.sources.map((s) => s.ref)));
    expect(r.sources[0]).toMatchObject({ value: "€169,041", confidence: "High" });
  });

  it("shows no euros to a role that sees hours only", () => {
    const hours = (f: ReportInput["wholeLoss"][number]) =>
      f.figure.unit === "eur_cents" ? { ...f, figure: { ...f.figure, unit: "h" } } : f;
    const base = input();
    const r = buildReport(
      input({ monthLoss: base.monthLoss.map(hours), wholeLoss: base.wholeLoss.map(hours) }),
    );
    expect(allText(r)).not.toContain("€");
  });

  it("names a shared team and the steps it covers", () => {
    const r = buildReport(
      input({
        detection: {
          ...detection,
          resource_code: "FINISH-TEAM",
          reasons: [
            ...detection.reasons,
            { code: "team_covers", values: { team: "FINISH-TEAM", steps: "FINISH, PACK" } },
          ],
        },
      }),
    );
    expect(allText(r)).toContain("FINISH-TEAM) limits your output.");
    expect(allText(r)).toContain("is a team shared by several steps (");
    expect(allText(r)).toContain("(FINISH), ");
  });

  it("says so when no step limits output", () => {
    const r = buildReport(
      input({
        detection: {
          ...detection,
          kind: "market",
          resource_code: null,
          reasons: [{ code: "no_machine_binding", values: { top: "PNT-01", busy_pct: 42.1 } }],
          methods: detection.methods.map((m) => ({ ...m, resource_code: null })),
        },
        utilisation: [
          {
            ...fact("utilisation_pct", "x", 42.1, "pct"),
            family: "utilisation" as never,
            reason_code: null,
          },
        ],
      }),
    );
    expect(r.sections.map((s) => s.key)).not.toContain("cost");
    expect(allText(r)).toContain("No step limits you");
    expect(allText(r)).toContain("42.1%");
    expect(allText(r)).toContain("Busy time: No step (closest: Paint line (PNT-01)). Evidence:");
  });
});

describe("results report PDF", () => {
  it("writes the whole report, sources included, as a PDF", async () => {
    const r = buildReport(input());
    const bytes = await reportPdf(r, {
      sources: "Where every number comes from",
      sourcesIntro: "Intro",
      formula: "How it is worked out",
      inputs: "Made from",
      period: "Data period",
      confidence: "Confidence",
      formulaId: "Formula id",
      page: (n, total) => `Page ${n} of ${total}`,
    });
    expect(new TextDecoder().decode(bytes.slice(0, 5))).toBe("%PDF-");
    expect(bytes.length).toBeGreaterThan(2000);
  });

  it("fails loudly on a character the PDF fonts cannot write", async () => {
    const r = { ...buildReport(input()), title: "Report ✓" };
    await expect(
      reportPdf(r, {
        sources: "",
        sourcesIntro: "",
        formula: "",
        inputs: "",
        period: "",
        confidence: "",
        formulaId: "",
        page: () => "",
      }),
    ).rejects.toThrow();
  });
});
