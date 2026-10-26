"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { Panel } from "@cip/ui";
import { api, problemOf } from "@/lib/api/client";
import { Count } from "./Figure";

/** Before the run: what this upload will change in the plant, from the engine (ADR-0010). */
export function ImportPreview({ importId, files }: { importId: string; files: string }) {
  const t = useTranslations("import.preview");
  const tl = useTranslations("import.changes.lists");
  const tf = useTranslations("figure");
  const locale = useLocale();
  const preview = useQuery({
    queryKey: ["import-preview", importId, files],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/imports/{import_id}/preview", {
        params: { path: { import_id: importId } },
      });
      if (!data) throw new Error(problemOf(error, response.status).message);
      return data;
    },
  });
  const day = (iso: string | null | undefined) =>
    iso ? new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(iso)) : "—";
  const p = preview.data;
  const count = (value: number, key: string) => (
    <Count value={value} label={t(`count.${key}`)} source={{ what: tf(`src.preview.${key}`) }} />
  );

  return (
    <Panel label={t("label")}>
      {preview.isPending && (
        <p role="status" className="m-0 text-sm text-muted">
          {t("working")}
        </p>
      )}
      {preview.error && (
        <p role="alert" className="m-0 text-sm text-bad">
          {t("failed", { reason: preview.error.message })}
        </p>
      )}
      {p && (
        <div className="flex flex-col gap-2 text-sm">
          {p.warnings.map((w) => (
            <p key={w.code} role="alert" className="m-0 font-medium text-warn">
              <span aria-hidden="true">▲</span>{" "}
              {t(`warning.${w.code}`, { items: w.items.join(", "), count: w.count })}
            </p>
          ))}
          <ul className="m-0 flex list-disc flex-col gap-1 pl-5">
            <li>
              {t("eventsLead")} {count(p.events_added, "added")} {t("eventsAdded")}
              {p.events_removed > 0 && (
                <>
                  {", "}
                  {count(p.events_removed, "removed")} {t("eventsRemoved")}
                </>
              )}
              {" · "}
              {t("period", {
                from: `${day(p.period_before[0])} → ${day(p.period_before[1])}`,
                to: `${day(p.period_after[0])} → ${day(p.period_after[1])}`,
              })}
            </li>
            {p.lists.map((c) => (
              <li key={c.name}>
                {t("list", { list: tl(c.name as "resources"), before: c.before, after: c.after })}
                {c.new.length > 0 && ` · ${t("new", { items: c.new.join(", ") })}`}
                {c.gone.length > 0 && ` · ${t("gone", { items: c.gone.join(", ") })}`}
              </li>
            ))}
            {p.lists.length === 0 && <li>{t("noListChanges")}</li>}
          </ul>
          <p className="m-0 text-xs text-muted">{t("note")}</p>
        </div>
      )}
    </Panel>
  );
}
