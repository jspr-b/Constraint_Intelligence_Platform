"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Button, Panel } from "@cip/ui";
import { api, problemOf } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Count } from "./Figure";
import { useView } from "./ViewContext";

export type Correction = components["schemas"]["CorrectionOut"];

const TH = "px-3 py-2 text-left text-[11px] font-medium uppercase tracking-[0.08em] text-muted";
const TD = "px-3 py-2 align-top";

export function useCorrections(plant: string | null) {
  return useQuery({
    queryKey: ["corrections", plant],
    enabled: Boolean(plant),
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/corrections", {
          params: { path: { plant_code: plant ?? "" } },
        })
      ).data ?? [],
  });
}

/** What a correction did, in plain words: "line 101 of mes_events.csv: Tijdstip … → …". */
export function useCorrectionText(): (c: Correction) => string {
  const t = useTranslations("corrections");
  const tl = useTranslations("import.changes.lists");
  const tc = useTranslations("calendar.kind");
  const locale = useLocale();
  return (c) => {
    if (c.action === "remove") {
      const key = c.target_key ?? [];
      if (c.target === "calendar_windows" && key.length === 4) {
        // [step, kind, start, end] in UTC, shown in plant local time like the Calendar page.
        const [step = "", kind = "", start = "", end = ""] = key;
        const at = (iso: string, day: boolean) =>
          new Intl.DateTimeFormat(locale, {
            timeZone: c.timezone_iana,
            ...(day ? { weekday: "short", day: "numeric", month: "short" } : {}),
            hour: "2-digit",
            minute: "2-digit",
            hourCycle: "h23",
          }).format(new Date(iso));
        const what = `${tc.has(kind) ? tc(kind) : kind} ${step}, ${at(start, true)} – ${at(end, false)}`;
        return t("removed", { list: tl("calendar"), key: what });
      }
      const list = c.target === "stations" ? "stations" : "resources";
      return t("removed", { list: tl(list), key: key.join(" · ") });
    }
    const where = t("where", { line: c.line ?? 0, file: c.file ?? "" });
    return c.action === "exclude"
      ? t("leftOut", { where })
      : t("set", { where, column: c.column ?? "", from: c.original ?? "—", to: c.value ?? "" });
  };
}

/** Every row fixed, left out or removed in the app for the plant; on Data quality and Report. */
export function CorrectionsList({ plant }: { plant: string }) {
  const t = useTranslations("corrections");
  const tf = useTranslations("figure");
  const troles = useTranslations("roles");
  const locale = useLocale();
  const corrections = useCorrections(plant);
  const text = useCorrectionText();
  const view = useView();
  const canUndo =
    (view?.decisions.has("import_run_diagnostic") ?? false) && view?.preview === false;
  const queries = useQueryClient();
  const undo = useMutation({
    mutationFn: async (id: string) => {
      const { data, error, response } = await api.DELETE("/corrections/{correction_id}", {
        params: { path: { correction_id: id } },
      });
      if (!data) throw new Error(problemOf(error, response.status).message);
      return data;
    },
    onSettled: () => void queries.invalidateQueries(),
  });
  const all = corrections.data ?? [];
  const inUse = all.filter((c) => !c.undone);
  const when = (iso: string) =>
    new Intl.DateTimeFormat(locale, {
      dateStyle: "medium",
      timeStyle: "short",
      hourCycle: "h23",
    }).format(new Date(iso));

  return (
    <Panel label={t("label")} status={<span>{t("count", { count: inUse.length })}</span>}>
      <div id="fixed-rows" className="flex flex-col gap-2 text-sm">
        {all.length === 0 ? (
          <p className="m-0">
            {t("none")} <Link href="/import">{t("toImport")}</Link>
          </p>
        ) : (
          <>
            <p className="m-0">
              <Count
                value={inUse.length}
                label={t("label")}
                source={{ what: tf("src.corrections"), href: "/import", page: t("importPage") }}
              />{" "}
              {t("lead")}{" "}
              <a
                href={`/api/plants/${encodeURIComponent(plant)}/corrections.csv`}
                download
                className="text-accent"
              >
                {t("download")}
              </a>
            </p>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <th scope="col" className={TH}>
                      {t("colWhat")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("colWhy")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("colBy")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("colStatus")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {all.map((c) => (
                    <tr key={c.correction_id} className="border-t border-line">
                      <td className={`${TD} font-mono text-xs`}>{text(c)}</td>
                      <td className={TD}>{c.reason}</td>
                      <td className={`${TD} text-xs`}>
                        {troles.has(c.role) ? troles(c.role) : c.role}, {when(c.created_at)}
                      </td>
                      <td className={`${TD} text-xs`}>
                        {c.undone
                          ? t("undone", { when: c.undone_at ? when(c.undone_at) : "—" })
                          : t("inUse")}
                        {!c.undone && canUndo && (
                          <Button
                            variant="ghost"
                            aria-label={t("undoOf", { what: text(c) })}
                            isDisabled={undo.isPending}
                            onPress={() => undo.mutate(c.correction_id)}
                          >
                            {t("undo")}
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {undo.error && (
          <p role="alert" className="m-0 text-sm text-bad">
            {undo.error.message}
          </p>
        )}
        <p className="m-0 text-xs text-muted">{t("note")}</p>
      </div>
    </Panel>
  );
}
