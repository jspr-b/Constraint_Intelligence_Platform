"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { Button, Panel } from "@cip/ui";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Count } from "./Figure";
import type { ImportEvents } from "./ImportChanges";

type ImportOut = components["schemas"]["ImportOut"];

const TH = "px-3 py-2 text-left text-[11px] font-medium uppercase tracking-[0.08em] text-muted";
const TD = "px-3 py-2 align-top";

/** Every import of the plant (ADR-0010): when, by which role, files, period, status. */
export function ImportHistory({
  plant,
  imports,
  shown,
  onOpen,
}: {
  plant: string;
  imports: ImportOut[];
  shown: string | undefined;
  onOpen: (id: string) => void;
}) {
  const t = useTranslations("import.history");
  const ts = useTranslations("import.status");
  const troles = useTranslations("roles");
  const tf = useTranslations("figure");
  const locale = useLocale();
  const inUse = useQuery({
    queryKey: ["data-in-use", plant, imports.map((i) => `${i.import_id}:${i.status}`).join()],
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/data-in-use", {
          params: { path: { plant_code: plant } },
        })
      ).data ?? [],
  });
  const stamp = (iso: string) =>
    new Intl.DateTimeFormat(locale, {
      dateStyle: "medium",
      timeStyle: "short",
      hourCycle: "h23",
    }).format(new Date(iso));
  const day = (iso: string | null | undefined) =>
    iso ? new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(iso)) : "—";
  const role = (r: string | null | undefined) =>
    !r ? "—" : r === "system" ? t("system") : troles.has(r) ? troles(r) : r;
  const uses = inUse.data ?? [];
  const when = new Map(imports.map((i) => [i.import_id, stamp(i.created_at)]));

  return (
    <Panel label={t("label")} status={<span>{t("count", { count: imports.length })}</span>}>
      {uses.length > 0 && (
        <p className="m-0 mb-3 text-sm">
          {t("inUse")}{" "}
          {uses
            .map((u) =>
              t("inUseItem", {
                when: when.get(u.import_id) ?? stamp(u.created_at),
                events: u.events.toLocaleString(locale),
                lists: u.lists.length,
              }),
            )
            .join(" · ")}
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              <th scope="col" className={TH}>
                {t("colUploaded")}
              </th>
              <th scope="col" className={TH}>
                {t("colBy")}
              </th>
              <th scope="col" className={TH}>
                {t("colFiles")}
              </th>
              <th scope="col" className={TH}>
                {t("colPeriod")}
              </th>
              <th scope="col" className={TH}>
                {t("colAdded")}
              </th>
              <th scope="col" className={TH}>
                {t("colStatus")}
              </th>
              <th scope="col" className={TH}>
                <span className="sr-only">{t("colOpen")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {imports.map((i) => {
              const events = i.report?.events as ImportEvents | undefined;
              const isShown = i.import_id === shown;
              return (
                <tr
                  key={i.import_id}
                  className={`border-t border-line ${isShown ? "bg-raised" : ""}`}
                >
                  <td className={`${TD} font-mono text-xs`}>{stamp(i.created_at)}</td>
                  <td className={TD}>{role(i.by_role)}</td>
                  <td className={TD}>
                    <span className="font-mono text-xs">
                      {i.files.map((f) => f.name).join(", ")}
                    </span>
                    {i.replaces && (
                      <span className="block text-xs text-muted">
                        {t("newVersionOf", { when: when.get(i.replaces) ?? "—" })}
                      </span>
                    )}
                  </td>
                  <td className={`${TD} font-mono text-xs`}>
                    {events
                      ? `${day(events.period_added.start_at)} → ${day(events.period_added.end_at)}`
                      : "—"}
                  </td>
                  <td className={TD}>
                    {events ? (
                      <Count
                        value={events.added}
                        label={t("colAdded")}
                        source={{ what: tf("src.importEvents.added") }}
                      />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className={TD}>
                    {ts(i.status as "done")}
                    {i.replaced_by && (
                      <span className="block text-xs text-muted">
                        {t("replacedBy", { when: when.get(i.replaced_by) ?? "—" })}
                      </span>
                    )}
                  </td>
                  <td className={TD}>
                    {isShown ? (
                      <span className="text-xs text-muted">{t("showing")}</span>
                    ) : (
                      <Button
                        variant="ghost"
                        aria-label={t("openOf", { when: stamp(i.created_at) })}
                        onPress={() => onOpen(i.import_id)}
                      >
                        {t("open")}
                      </Button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="m-0 mt-2 text-xs text-muted">{t("note")}</p>
    </Panel>
  );
}
