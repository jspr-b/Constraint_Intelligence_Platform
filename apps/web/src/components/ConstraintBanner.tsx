"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { ConstraintMarker, isMissing, MicroLabel, type FigureLike } from "@cip/ui";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Figure } from "./Figure";
import { termTags } from "./terms";

type Detection = components["schemas"]["DetectionOut"];
type Reason = components["schemas"]["ReasonOut"];
type Fact = components["schemas"]["FactOut"];
export type DetectionPeriod = { period_kind: "all" | "month" | "week"; period_start_at?: string };

/** The plant's constraint for a period, read from the stored detection. */
export function useDetection(plant: string | null, period: DetectionPeriod) {
  return useQuery({
    queryKey: ["detection", plant, period],
    enabled: plant !== null,
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/detection", {
          params: { path: { plant_code: plant ?? "" }, query: period },
        })
      ).data ?? null,
    refetchInterval: (q) => (q.state.data?.run?.status === "calculating" ? 3000 : false),
  });
}

/** One reason in plain words; machine codes become names. */
function ReasonText({ reason, label }: { reason: Reason; label: (code: string) => string }) {
  const t = useTranslations("detection.reason");
  const v = reason.values;
  const machine = (key: string) => (v[key] && v[key] !== "none" ? label(String(v[key])) : "");
  if (reason.code.startsWith("method_differs_")) {
    const method = reason.code.slice("method_differs_".length);
    return (
      <span data-raw>
        {v.machine === "none"
          ? t("differsNone", { method: t(`method.${method}`), top: machine("top") || "—" })
          : t("differs", { method: t(`method.${method}`), machine: machine("machine") })}
      </span>
    );
  }
  switch (reason.code) {
    case "methods_agree":
      return (
        <span data-raw>
          {t("agree", {
            count: Number(v.count),
            total: Number(v.total),
            machine: machine("machine"),
          })}
        </span>
      );
    case "no_machine_binding":
      return (
        <span data-raw>
          {t("market", { machine: machine("top") || "—", busy: Math.round(Number(v.busy_pct)) })}
        </span>
      );
    case "queue_with_spare_time":
      return (
        <span data-raw>
          {t("queue_with_spare_time", {
            machine: machine("machine") || "—",
            busy: Math.round(Number(v.busy_pct)),
          })}
        </span>
      );
    case "material_late":
      return <span data-raw>{t("material", { share: Math.round(Number(v.share_pct)) })}</span>;
    case "weak_evidence":
      return <span>{t("weak", { level: t(`level.${String(v.level)}`) })}</span>;
    case "data_gap":
      return <span>{t("dataGap")}</span>;
    case "team_covers":
      return (
        <span data-raw>
          {t("teamCovers", {
            team: machine("team"),
            steps: String(v.steps)
              .split(", ")
              .map((code) => label(code))
              .join(", "),
          })}
        </span>
      );
    default:
      return <span>{t("other")}</span>;
  }
}

/**
 * The answer: which machine limits output (or that none does), how many checks agree and how
 * sure we are. Every number opens its calculation.
 */
/** What the bottleneck lost in the period: hours, euros (or why not) and the biggest cause. */
function LostLine({ loss }: { loss: Fact[] }) {
  const t = useTranslations("detection.loss");
  const pick = (measure: string, cause: string) =>
    loss.find((f) => f.measure === measure && f.reason_code === cause)?.figure;
  const hours = pick("lost_h", "total");
  const money = pick("lost_eur_cents", "total");
  if (!hours) return null;
  const causes = loss
    .filter((f) => f.measure === "lost_h" && f.reason_code !== "total")
    .filter((f) => !isMissing(f.figure.value));
  const top = causes.sort((a, b) => Number(b.figure.value) - Number(a.figure.value))[0];
  return (
    <div className="flex flex-col gap-1 border-t border-line pt-3 text-sm">
      <p className="m-0 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-muted">{t("label")}</span>
        <Figure figure={hours as FigureLike} label={t("hours")} />
        {money && money.unit === "eur_cents" && (
          <>
            <span className="text-muted">{t("worth")}</span>
            <Figure figure={money as FigureLike} label={t("euros")} />
          </>
        )}
      </p>
      {money && money.unit === "eur_cents" && isMissing(money.value) && (
        <p className="m-0 text-muted">{t("noEuros")}</p>
      )}
      {top && (
        <p className="m-0 flex flex-wrap items-baseline gap-x-2">
          <span className="text-muted">
            {t("biggest", { cause: t(`cause.${top.reason_code}`) })}
          </span>
          <Figure
            figure={top.figure as FigureLike}
            label={t("causeHours", { cause: t(`cause.${top.reason_code}`) })}
          />
        </p>
      )}
    </div>
  );
}

export function ConstraintBanner({
  detection,
  label,
  periodName,
  loss = [],
}: {
  detection: Detection;
  label: (code: string) => string;
  periodName: string;
  loss?: Fact[];
}) {
  const t = useTranslations("detection");
  const d = detection;
  const title =
    d.kind === "internal" && d.resource_code ? (
      <span className="flex flex-wrap items-baseline gap-2 pt-5">
        <ConstraintMarker tag={t("tag")}>
          <span className="px-1 font-display text-xl" data-raw>
            {label(d.resource_code)}
          </span>
        </ConstraintMarker>
        <span className="text-sm">{t.rich("internal", termTags)}</span>
      </span>
    ) : (
      <span className="text-base font-medium">{t(d.kind)}</span>
    );
  return (
    <section
      aria-label={t("label")}
      className="flex flex-col gap-3 rounded-panel border border-line-strong bg-surface p-4"
      data-detection={d.resource_code ?? d.kind}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <MicroLabel>{t("heading", { period: periodName })}</MicroLabel>
        <span className="flex items-center gap-3 text-sm">
          <span className="inline-flex items-baseline gap-1">
            <span className="text-muted">{t("agreement")}</span>
            <Figure figure={d.agreement as FigureLike} label={t("agreement")} />
          </span>
          <span>
            <span className="text-muted">{t.rich("confidence", termTags)}</span>{" "}
            <span className="font-medium">{t(`reason.level.${d.confidence}`)}</span>
          </span>
        </span>
      </div>
      {title}
      <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-sm">
        {d.reasons.map((r, i) => (
          <li key={`${r.code}-${i}`}>
            <ReasonText reason={r} label={label} />
          </li>
        ))}
      </ul>
      {d.kind === "internal" && <LostLine loss={loss} />}
      <details className="text-sm">
        <summary className="cursor-pointer text-accent">
          <span data-raw>{t("howFound")}</span>
        </summary>
        <p className="m-0 mt-2 text-muted">{t("howFoundHelp")}</p>
        <table className="mt-2 w-full border-collapse">
          <thead>
            <tr className="border-b border-line text-left text-micro uppercase tracking-[var(--tracking-micro)] text-muted">
              <th className="px-2 py-1 font-medium">{t("colMethod")}</th>
              <th className="px-2 py-1 font-medium">{t("colPoints")}</th>
              <th className="px-2 py-1 font-medium">{t("colEvidence")}</th>
            </tr>
          </thead>
          <tbody>
            {d.methods.map((m) => (
              <tr key={m.method} className="border-b border-line">
                <td className="px-2 py-1">
                  <span className="block font-medium first-letter:uppercase">
                    {t(`reason.method.${m.method}`)}
                  </span>
                  <span className="block text-xs text-muted" data-raw>
                    {t(`methodHelp.${m.method}`)}
                  </span>
                </td>
                <td className="px-2 py-1" data-raw>
                  {m.resource_code
                    ? label(m.resource_code)
                    : t("noneBinding", { top: m.top_code ? label(m.top_code) : "—" })}
                </td>
                <td className="px-2 py-1 whitespace-nowrap">
                  <Figure
                    figure={m.evidence as FigureLike}
                    label={t(`reason.method.${m.method}`)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
