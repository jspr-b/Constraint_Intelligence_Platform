"use client";

import { useLocale, useTranslations } from "next-intl";
import { Panel } from "@cip/ui";
import { Count } from "./Figure";

type Period = { start_at: string | null; end_at: string | null };
export type ImportEvents = {
  added: number;
  already_there: number;
  changed: number;
  repeated_in_file: number;
  in_plant: number;
  period_added: Period;
  plant_period: Period;
};

/** What one import changed in the plant's data (ADR-0010): events added, lists replaced. */
export function ImportChanges({ events, replaced }: { events: ImportEvents; replaced: string[] }) {
  const t = useTranslations("import.changes");
  const tf = useTranslations("figure");
  const locale = useLocale();
  const date = (iso: string | null) =>
    iso ? new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(iso)) : "—";
  const count = (key: "added" | "already_there" | "changed" | "repeated_in_file" | "in_plant") => (
    <Count
      value={events[key]}
      label={t(`count.${key}`)}
      source={{ what: tf(`src.importEvents.${key}`) }}
    />
  );
  return (
    <Panel label={t("label")}>
      <dl className="m-0 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted">{t("count.added")}</dt>
        <dd className="m-0">{count("added")}</dd>
        <dt className="text-muted">{t("count.already_there")}</dt>
        <dd className="m-0">
          {count("already_there")}{" "}
          <span className="text-xs text-muted">{t("alreadyThereNote")}</span>
        </dd>
        {events.changed > 0 && (
          <>
            <dt className="text-muted">{t("count.changed")}</dt>
            <dd className="m-0">{count("changed")}</dd>
          </>
        )}
        {events.repeated_in_file > 0 && (
          <>
            <dt className="text-muted">{t("count.repeated_in_file")}</dt>
            <dd className="m-0">
              {count("repeated_in_file")}{" "}
              <span className="text-xs text-muted">{t("repeatedNote")}</span>
            </dd>
          </>
        )}
        <dt className="text-muted">{t("periodAdded")}</dt>
        <dd className="m-0 font-mono text-xs">
          {date(events.period_added.start_at)} → {date(events.period_added.end_at)}
        </dd>
        <dt className="text-muted">{t("plantNow")}</dt>
        <dd className="m-0">
          <span className="font-mono text-xs">
            {date(events.plant_period.start_at)} → {date(events.plant_period.end_at)}
          </span>{" "}
          · {count("in_plant")} {t("eventsWord")}
        </dd>
        <dt className="text-muted">{t("listsReplaced")}</dt>
        <dd className="m-0">
          {replaced.length > 0 ? replaced.map((l) => t(`lists.${l}`)).join(", ") : t("noLists")}
        </dd>
      </dl>
      <p className="m-0 mt-2 text-xs text-muted">{t("rule")}</p>
    </Panel>
  );
}
