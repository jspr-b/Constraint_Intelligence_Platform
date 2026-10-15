"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { KpiReadout, Panel } from "@cip/ui";
import { api } from "@/lib/api/client";
import { EmptyState } from "../EmptyState";
import { PageHeader } from "../PageHeader";
import { PlantPicker, usePlant } from "../PlantPicker";

const TH =
  "px-3 py-2 text-left text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted";
const TD = "px-3 py-2";
const IMPACT_GLYPH: Record<string, string> = { high: "▲", medium: "◆", low: "·", none: "○" };

/** Data quality page (mockup D2): the engine's score, rejected rows per file and gaps. */
export function DataQualityPage() {
  const t = useTranslations("quality");
  const locale = useLocale();
  const picker = usePlant();
  const { plant } = picker;
  const [onlyIssues, setOnlyIssues] = useState(true);
  const report = useQuery({
    queryKey: ["data-quality", plant],
    enabled: plant !== null,
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/data-quality", {
          params: { path: { plant_code: plant ?? "" } },
        })
      ).data ?? null,
  });
  const q = report.data;
  const date = (iso: string) =>
    new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(iso));
  const stamp = (iso: string) =>
    new Intl.DateTimeFormat(locale, {
      dateStyle: "medium",
      timeStyle: "short",
      hourCycle: "h23",
      timeZone: "UTC",
    }).format(new Date(iso));
  const files = (q?.files ?? []).filter((f) => !onlyIssues || f.rejected > 0);
  const rejected = (q?.files ?? []).reduce((n, f) => n + f.rejected, 0);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        page="data"
        headline={
          q?.import_id && q.imported_at
            ? t("headline", { at: stamp(q.imported_at), gaps: q.gaps.length })
            : undefined
        }
        actions={<PlantPicker {...picker} />}
      />
      {q && !q.import_id && (
        <EmptyState title={t("noImportTitle")}>
          {t("noImport")} <Link href="/import">{t("toImport")}</Link>
        </EmptyState>
      )}
      {q?.score && q.rows && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Panel label={t("score")}>
              <KpiReadout
                label={t("scoreOf")}
                figure={q.score}
                locale={locale}
                missingLabel={t("missing")}
              />
            </Panel>
            <Panel label={t("rowsImported")}>
              <KpiReadout
                label={t("rejected", { rejected })}
                figure={q.rows}
                locale={locale}
                missingLabel={t("missing")}
              />
            </Panel>
            <Panel label={t("eventPeriod")}>
              {q.event_period_weeks ? (
                <KpiReadout
                  label={t("weeksLabel")}
                  figure={q.event_period_weeks}
                  locale={locale}
                  missingLabel={t("missing")}
                />
              ) : (
                <p className="m-0 text-sm text-muted">{t("missing")}</p>
              )}
              {q.event_period_start_at && q.event_period_end_at && (
                <p className="m-0 mt-1 font-mono text-xs text-muted">
                  {date(q.event_period_start_at)} → {date(q.event_period_end_at)}
                </p>
              )}
            </Panel>
            <Panel label={t("files")}>
              <p className="m-0 font-display text-2xl font-bold leading-none">
                {q.files_required - q.files_missing.length}
                <span className="text-base text-muted"> / {q.files_required}</span>
              </p>
              <p className="m-0 mt-1 text-xs text-muted">
                {q.files_missing.length === 0
                  ? t("allFiles")
                  : t("missingFiles", { files: q.files_missing.join(", ") })}
              </p>
            </Panel>
          </div>
          <Panel
            label={t("filesLabel")}
            status={
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={onlyIssues}
                  onChange={(e) => setOnlyIssues(e.target.checked)}
                />
                {t("onlyIssues")}
              </label>
            }
          >
            {files.length === 0 ? (
              <p className="m-0 text-sm text-muted">{t("noIssues")}</p>
            ) : (
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    <th scope="col" className={TH}>
                      {t("file")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("rows")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("rejectedCol")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("status")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("reasons")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((f) => (
                    <tr key={f.file} className="border-t border-line">
                      <td className={`${TD} font-mono text-xs`}>{f.file}</td>
                      <td className={`${TD} font-mono text-xs`}>{f.rows.toLocaleString(locale)}</td>
                      <td className={`${TD} font-mono text-xs`}>
                        {f.rejected.toLocaleString(locale)}
                      </td>
                      <td className={TD}>
                        <span aria-hidden="true">{f.rejected > 0 ? "▲" : "●"}</span>{" "}
                        {f.rejected > 0 ? t("hasRejected") : t("ok")}
                      </td>
                      <td className={`${TD} text-xs text-muted`}>
                        {Object.entries(f.reasons)
                          .map(([reason, n]) => `${reason} ${n}`)
                          .join(" · ") || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
          <Panel label={t("gapsLabel")} status={<span>{t("missingShown")}</span>}>
            {q.gaps.length === 0 ? (
              <p className="m-0 text-sm text-muted">{t("noGaps")}</p>
            ) : (
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    <th scope="col" className={TH}>
                      {t("gap")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("machine")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("impact")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("fix")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {q.gaps.map((g, i) => (
                    <tr
                      key={`${g.code}-${g.resource_code ?? "all"}-${i}`}
                      className="border-t border-line"
                    >
                      <td className={TD}>{g.description}</td>
                      <td className={`${TD} font-mono text-xs`}>
                        {g.resource_code ?? t("allMachines")}
                      </td>
                      <td className={TD}>
                        <span aria-hidden="true">{IMPACT_GLYPH[g.confidence_impact] ?? "·"}</span>{" "}
                        {t(`impactLevel.${g.confidence_impact}`)}
                      </td>
                      <td className={`${TD} text-xs text-muted`}>{g.fix}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
