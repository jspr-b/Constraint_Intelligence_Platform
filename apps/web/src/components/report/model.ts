/**
 * The results report as plain data: sections of lines, and every number with its source.
 *
 * The page and the PDF are both drawn from this one model, so they always say the same thing.
 * Nothing is calculated here: every number is an engine Figure or a count from the import,
 * only put in order and given words.
 */
import { formatFigure, isMissing, type FigureLike } from "@cip/ui";
import type { components } from "@/lib/api/schema";

type Detection = components["schemas"]["DetectionOut"];
type Fact = components["schemas"]["FactOut"];
type Quality = components["schemas"]["DataQualityOut"];

/** Root translator (next-intl `useTranslations()`), passed in so the model stays pure. */
export type Translate = (key: string, values?: Record<string, string | number>) => string;

export interface CountSource {
  what: string;
  href?: string;
  page?: string;
}

export type Seg =
  | { text: string }
  | { figure: FigureLike; label: string; ref: number }
  | { count: number; shown: string; label: string; source: CountSource };

export type Line = Seg[];

export interface Section {
  key: string;
  heading: string;
  lines: Line[];
}

/** One numbered source in the appendix: how a number on the report was worked out. */
export interface Source {
  ref: number;
  figure: FigureLike;
  label: string;
  value: string;
  formula: string;
  inputs: string[];
  period: string;
  confidence: string;
  formulaId: string;
}

export interface Report {
  title: string;
  plant: string;
  period: string;
  made: string;
  sections: Section[];
  sources: Source[];
  fileName: string;
}

export interface ReportInput {
  plantCode: string;
  plantName: string;
  detection: Detection;
  /** The last full month the data covers, with its loss facts. */
  month?: { period_kind: string; period_start_at: string; period_end_at: string };
  monthLoss: Fact[];
  wholeLoss: Fact[];
  /** Utilisation facts of the whole period (used when no machine limits output). */
  utilisation: Fact[];
  quality: Quality | null;
  label: (code: string) => string;
  periodName: (p: { period_kind: string; period_start_at: string } | undefined) => string;
  t: Translate;
  locale: string;
  formulaText: (figure: FigureLike) => string;
  inputLines: (figure: FigureLike) => string[];
  madeAt: Date;
}

const CAUSES = ["breakdowns", "setup", "starved", "blocked", "breaks", "maintenance", "scrap"];

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
/** "2026-07-20" in the viewer's time zone, the same day the page shows. For the file name. */
const day = (iso: string) =>
  new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit" }).format(
    new Date(iso),
  );

export function buildReport(input: ReportInput): Report {
  const { detection: d, t, locale, label } = input;
  const sources: Source[] = [];
  const refs = new Map<FigureLike, number>();
  const dateFmt = new Intl.DateTimeFormat(locale, { dateStyle: "medium" });
  const date = (iso: string) => dateFmt.format(new Date(iso));
  const number = new Intl.NumberFormat(locale);

  const fig = (figure: FigureLike, figLabel: string): Seg => {
    let ref = refs.get(figure);
    if (ref === undefined) {
      ref = sources.length + 1;
      refs.set(figure, ref);
      const missing = isMissing(figure.value) ? figure.value : null;
      sources.push({
        ref,
        figure,
        label: figLabel,
        value: missing ? t("figure.missing") : formatFigure(figure, locale),
        formula: input.formulaText(figure),
        inputs: input.inputLines(figure),
        period:
          figure.period_start_at && figure.period_end_at
            ? t("report.periodRange", {
                start: date(figure.period_start_at),
                end: date(figure.period_end_at),
              })
            : t("figure.periodAll"),
        confidence: t(`figure.level.${figure.confidence}`),
        formulaId: figure.formula_id,
      });
    }
    return { figure, label: figLabel, ref };
  };
  const text = (s: string): Seg => ({ text: s });
  const count = (value: number, countLabel: string, source: CountSource): Seg => ({
    count: value,
    shown: number.format(value),
    label: countLabel,
    source,
  });
  const pick = (facts: Fact[], measure: string, cause: string) =>
    facts.find((f) => f.measure === measure && f.reason_code === cause);
  const euros = (f: Fact | undefined) =>
    f && f.figure.unit === "eur_cents" && !isMissing(f.figure.value) ? f : undefined;

  const internal = d.kind === "internal" && !!d.resource_code;
  const sections: Section[] = [];

  // 1. What limits output
  const answer: Line[] = [];
  if (internal && d.resource_code) {
    answer.push([text(t("report.limits", { machine: label(d.resource_code) }))]);
    const team = d.reasons.find((r) => r.code === "team_covers");
    if (team) {
      answer.push([
        text(
          t("detection.reason.teamCovers", {
            team: label(String(team.values.team)),
            steps: String(team.values.steps)
              .split(", ")
              .map((code) => label(code))
              .join(", "),
          }),
        ),
      ]);
    }
    const money = pick(input.monthLoss, "lost_eur_cents", "total");
    const hours = pick(input.monthLoss, "lost_h", "total");
    const moneyEur = euros(money);
    if (input.month && moneyEur) {
      answer.push([
        text(t("overview.costAbout")),
        fig(moneyEur.figure as FigureLike, t("overview.costLabel")),
        text(t("overview.inMonth", { month: input.periodName(input.month) })),
      ]);
    } else if (input.month && hours) {
      answer.push([
        text(t("overview.lostAbout")),
        fig(hours.figure as FigureLike, t("overview.hoursLabel")),
        text(t("overview.hoursInMonth", { month: input.periodName(input.month) })),
      ]);
    }
    if (money && money.figure.unit === "eur_cents" && isMissing(money.figure.value)) {
      answer.push([text(t("overview.noEuros"))]);
    }
  } else {
    answer.push([text(t(`overview.${d.kind}`))]);
    const top = input.utilisation
      .filter((f) => f.measure === "utilisation_pct" && !isMissing(f.figure.value))
      .sort((a, b) => Number(b.figure.value) - Number(a.figure.value))[0];
    if (top) {
      answer.push([
        text(t("overview.busiest", { machine: label(top.resource_code) })),
        fig(top.figure as FigureLike, t("overview.busyLabel")),
        text(t("overview.busiestTail")),
      ]);
    }
  }
  sections.push({ key: "answer", heading: t("report.sections.answer"), lines: answer });

  // 2. What it cost: the whole data period, by cause
  if (internal) {
    const lines: Line[] = [];
    const totalH = pick(input.wholeLoss, "lost_h", "total");
    const totalEur = euros(pick(input.wholeLoss, "lost_eur_cents", "total"));
    if (totalH) {
      const line: Line = [
        text(t("report.costTotal")),
        fig(totalH.figure as FigureLike, t("overview.hoursLabel")),
      ];
      if (totalEur) line.push(fig(totalEur.figure as FigureLike, t("overview.costLabel")));
      lines.push(line);
    }
    const causes = CAUSES.flatMap((c) => {
      const h = pick(input.wholeLoss, "lost_h", c);
      return h && !isMissing(h.figure.value) && Number(h.figure.value) > 0 ? [{ c, h }] : [];
    }).sort((a, b) => Number(b.h.figure.value) - Number(a.h.figure.value));
    for (const { c, h } of causes) {
      const name = cap(t(`detection.loss.cause.${c}`));
      const line: Line = [
        text(`${name}:`),
        fig(h.figure as FigureLike, t("overview.causeHours", { cause: name })),
      ];
      const eur = euros(pick(input.wholeLoss, "lost_eur_cents", c));
      if (eur) line.push(fig(eur.figure as FigureLike, t("overview.causeEuros", { cause: name })));
      lines.push(line);
    }
    if (lines.length === 0) lines.push([text(t("report.noLoss"))]);
    lines.push([text(t("report.costNote"))]);
    sections.push({ key: "cost", heading: t("report.sections.cost"), lines });
  }

  // 3. How sure we are, and the evidence: the four checks
  const agree = d.reasons.find((r) => r.code === "methods_agree");
  const sure: Line[] = [
    [
      text(
        `${t(`overview.sure.${d.confidence}`)} ${
          agree
            ? t("overview.because", {
                count: Number(agree.values.count),
                total: Number(agree.values.total),
              })
            : t("overview.becauseMarket")
        }`,
      ),
    ],
    [
      text(t("report.agreement")),
      fig(d.agreement as FigureLike, t("overview.agreement")),
      text(t("report.confidence", { level: t(`overview.level.${d.confidence}`) })),
    ],
  ];
  for (const m of d.methods) {
    const method = cap(t(`detection.reason.method.${m.method}`));
    sure.push([
      text(
        `${method}: ${
          m.resource_code
            ? t("report.pointsAt", { machine: label(m.resource_code) })
            : t("report.pointsAtNone", {
                none: t("detection.noneBinding", { top: m.top_code ? label(m.top_code) : "-" }),
              })
        }`,
      ),
      fig(m.evidence as FigureLike, method),
    ]);
  }
  sections.push({ key: "sure", heading: t("report.sections.sure"), lines: sure });

  // 4. The data we used and what was missing
  const q = input.quality;
  const data: Line[] = [];
  if (q?.imported_at) {
    const when = date(q.imported_at);
    const from = (file: string): CountSource => ({
      what: t("figure.src.importFile", { file, date: when }),
      href: "/import",
      page: t("figure.pages.import"),
    });
    data.push([text(t("report.importOf", { date: when }))]);
    if (q.event_period_start_at && q.event_period_end_at) {
      const line: Line = [
        text(
          t("report.dataPeriod", {
            start: date(q.event_period_start_at),
            end: date(q.event_period_end_at),
          }),
        ),
      ];
      if (q.event_period_weeks) {
        line.push(fig(q.event_period_weeks as FigureLike, t("report.weeksLabel")));
      }
      data.push(line);
    }
    if (q.score) {
      data.push([
        text(t("report.score")),
        fig(q.score as FigureLike, t("report.scoreLabel")),
        text(t("report.scoreTail")),
      ]);
    }
    for (const f of q.files) {
      data.push([
        text(`${f.file}:`),
        count(f.rows, t("report.rowsLabel", { file: f.file }), from(f.file)),
        text(t("report.rows")),
        count(f.rejected, t("report.rejectedLabel", { file: f.file }), from(f.file)),
        text(t("report.rejected")),
      ]);
    }
    data.push([
      text(
        q.files_missing.length
          ? t("report.filesMissing", { files: q.files_missing.join(", ") })
          : t("report.filesAll"),
      ),
    ]);
    for (const g of q.gaps) {
      data.push([
        text(
          t("report.gap", {
            what: g.description.replace(/\.$/, ""),
            impact: t(`overview.level.${g.confidence_impact}`),
            fix: g.fix.replace(/\.$/, ""),
          }),
        ),
      ]);
    }
    if (q.gaps.length === 0) data.push([text(t("report.noGaps"))]);
  } else {
    data.push([text(t("report.noQuality"))]);
  }
  sections.push({ key: "data", heading: t("report.sections.data"), lines: data });

  // 5. Method
  const method: Line[] = [
    [text(t("report.method.checks"))],
    ...d.methods.map((m) => [
      text(
        `${cap(t(`detection.reason.method.${m.method}`))}: ${t(`detection.methodHelp.${m.method}`)}`,
      ),
    ]),
    [text(t("report.method.loss"))],
    [text(t("report.method.euros"))],
    [text(t("report.method.facts"))],
  ];
  sections.push({ key: "method", heading: t("report.sections.method"), lines: method });

  const start = day(d.period_start_at);
  const end = day(d.period_end_at);
  return {
    title: t("report.title"),
    plant: `${input.plantName} · ${input.plantCode}`,
    period: t("report.periodRange", { start: date(d.period_start_at), end: date(d.period_end_at) }),
    made: t("report.made", { date: date(input.madeAt.toISOString()) }),
    sections,
    sources,
    fileName: `results-report_${input.plantCode}_${start}_to_${end}.pdf`,
  };
}

/** A line as plain text, numbers followed by their source number: "€169,041 [1]". */
export function lineText(line: Line): string {
  return line
    .map((s) => ("text" in s ? s.text : "figure" in s ? `${formatSeg(s)} [${s.ref}]` : s.shown))
    .join(" ");
}

function formatSeg(s: { figure: FigureLike }): string {
  return isMissing(s.figure.value) ? "-" : formatFigure(s.figure, "en");
}
