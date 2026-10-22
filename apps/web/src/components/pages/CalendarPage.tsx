"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Button, Panel } from "@cip/ui";
import { api, ensureOk, problemOf } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { FIELD, Field, FormDialog } from "../FormDialog";
import { Count } from "../Figure";
import { PageHeader } from "../PageHeader";
import { ReadOnlyNote } from "../ReadOnlyNote";
import { PlantPicker, usePlant } from "../PlantPicker";
import { useView } from "../ViewContext";

type Window = components["schemas"]["WindowOut"];
type Kind = "shift" | "break" | "maintenance" | "holiday" | "overtime";

const TH =
  "px-3 py-2 text-left text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted";
const HATCH =
  "bg-[repeating-linear-gradient(135deg,var(--line-strong)_0_2px,transparent_2px_6px)] border border-line-strong";
/** Neutral fills only: status colours are reserved for status. Every kind has a glyph and label. */
const STYLE: Record<string, { cls: string; glyph: string }> = {
  shift: { cls: "bg-raised border border-line-strong", glyph: "▬" },
  break: { cls: HATCH, glyph: "▧" },
  covered: { cls: "bg-raised border border-dashed border-accent", glyph: "▭" },
  maintenance: { cls: "bg-line-strong border border-line-strong", glyph: "■" },
  holiday: { cls: "bg-line border border-line-strong", glyph: "◻" },
  overtime: { cls: "bg-raised border border-accent", glyph: "＋" },
};
const SHIFT_STYLE = { cls: "bg-raised border border-line-strong", glyph: "▬" };
const HOURS = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22];

function shiftDay(day: string, by: number): string {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + by);
  return d.toISOString().slice(0, 10);
}

/** Capacity calendar page (mockup F6), in plant local time. */
export function CalendarPage() {
  const t = useTranslations("calendar");
  const tf = useTranslations("figure");
  const locale = useLocale();
  const view = useView();
  const queries = useQueryClient();
  const picker = usePlant();
  const { plant } = picker;
  const canEdit = (view?.decisions.has("edit_setup_calendar") ?? false) && view?.preview === false;
  const [day, setDay] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cal = useQuery({
    queryKey: ["calendar", plant, day],
    enabled: plant !== null,
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/calendar", {
          params: { path: { plant_code: plant ?? "" }, query: day ? { day } : {} },
        })
      ).data ?? null,
  });
  const c = cal.data;
  const shown = day ?? c?.day ?? null;
  const refresh = () => queries.invalidateQueries({ queryKey: ["calendar", plant] });
  const clock = (iso: string) =>
    new Intl.DateTimeFormat(locale, {
      timeZone: c?.timezone_iana,
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).format(new Date(iso));
  const when = (iso: string) =>
    new Intl.DateTimeFormat(locale, {
      timeZone: c?.timezone_iana,
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).format(new Date(iso));
  const label = (w: Window) =>
    w.kind === "break" && w.covered ? t("kind.covered") : t(`kind.${w.kind as Kind}`);

  const change = useMutation({
    mutationFn: (call: () => Promise<{ response: Response; error?: unknown }>) => ensureOk(call()),
    onSettled: () => void refresh(),
  });
  const toggle = (w: Window) => {
    if (!plant) return;
    change.mutate(() =>
      api.PATCH("/plants/{plant_code}/calendar/windows/{window_id}", {
        params: { path: { plant_code: plant, window_id: w.id } },
        body: { covered: !w.covered },
      }),
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        page="calendar"
        headline={c ? t("headline", { tz: c.timezone_iana }) : undefined}
        actions={<PlantPicker {...picker} />}
      />
      {!canEdit && <ReadOnlyNote decision="edit_setup_calendar" />}
      {c && shown && (
        <>
          <div className="flex flex-wrap items-end gap-2">
            <Button aria-label={t("previousDay")} onPress={() => setDay(shiftDay(shown, -1))}>
              ‹
            </Button>
            <Field label={t("day")} className="flex flex-col gap-1">
              {(id) => (
                <input
                  id={id}
                  type="date"
                  value={shown}
                  onChange={(e) => e.target.value && setDay(e.target.value)}
                  className="min-h-9 rounded-control border border-line-strong bg-surface px-2 text-sm text-text"
                />
              )}
            </Field>
            <Button aria-label={t("nextDay")} onPress={() => setDay(shiftDay(shown, 1))}>
              ›
            </Button>
            {canEdit && (
              <FormDialog
                label={t("addWindow")}
                title={t("addWindow")}
                submitLabel={t("save")}
                cancelLabel={t("cancel")}
                error={error}
                onSubmit={async (form) => {
                  const date = String(form.get("date") ?? shown);
                  const { response, error } = await api.POST(
                    "/plants/{plant_code}/calendar/windows",
                    {
                      params: { path: { plant_code: c.plant_code } },
                      body: {
                        resource_code: String(form.get("machine") ?? ""),
                        kind: String(form.get("kind")) as Kind,
                        start_at: `${date}T${String(form.get("from"))}:00`,
                        end_at: `${String(form.get("toDate") || date)}T${String(form.get("to"))}:00`,
                        covered: false,
                      },
                    },
                  );
                  if (!response.ok)
                    return (setError(problemOf(error, response.status).message), false);
                  setError(null);
                  await refresh();
                  return true;
                }}
              >
                <Field label={t("machine")}>
                  {(id) => (
                    <select id={id} name="machine" className={FIELD}>
                      {c.machines.map((m) => (
                        <option key={m.resource_code} value={m.resource_code}>
                          {m.resource_code} · {m.name}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                <Field label={t("kindLabel")}>
                  {(id) => (
                    <select id={id} name="kind" className={FIELD}>
                      {(["shift", "break", "maintenance", "holiday", "overtime"] as const).map(
                        (k) => (
                          <option key={k} value={k}>
                            {t(`kind.${k}`)}
                          </option>
                        ),
                      )}
                    </select>
                  )}
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label={t("date")}>
                    {(id) => (
                      <input
                        id={id}
                        name="date"
                        type="date"
                        required
                        defaultValue={shown}
                        className={FIELD}
                      />
                    )}
                  </Field>
                  <Field label={t("from")}>
                    {(id) => (
                      <input
                        id={id}
                        name="from"
                        type="time"
                        required
                        defaultValue="06:00"
                        className={FIELD}
                      />
                    )}
                  </Field>
                  <Field label={t("toDate")}>
                    {(id) => (
                      <input
                        id={id}
                        name="toDate"
                        type="date"
                        defaultValue={shown}
                        className={FIELD}
                      />
                    )}
                  </Field>
                  <Field label={t("to")}>
                    {(id) => (
                      <input
                        id={id}
                        name="to"
                        type="time"
                        required
                        defaultValue="14:00"
                        className={FIELD}
                      />
                    )}
                  </Field>
                </div>
                <p className="m-0 text-xs text-muted">{t("localNote", { tz: c.timezone_iana })}</p>
              </FormDialog>
            )}
          </div>
          <Panel
            label={t("timelineLabel", {
              day: new Date(`${shown}T12:00:00Z`).toLocaleDateString(locale, {
                weekday: "long",
                day: "numeric",
                month: "long",
              }),
            })}
          >
            {c.machines.length === 0 ? (
              <p className="m-0 text-sm text-muted">{t("noMachines")}</p>
            ) : (
              <div className="flex flex-col gap-1.5">
                <div className="grid grid-cols-[96px_1fr] items-end gap-2">
                  <span />
                  <div className="relative h-4 font-mono text-micro text-muted" aria-hidden="true">
                    {HOURS.map((h) => (
                      <span key={h} className="absolute" style={{ left: `${(h / 24) * 100}%` }}>
                        {String(h).padStart(2, "0")}
                      </span>
                    ))}
                  </div>
                </div>
                {c.machines.map((m) => (
                  <div
                    key={m.resource_code}
                    className="grid grid-cols-[96px_1fr] items-center gap-2"
                  >
                    <span className="font-mono text-xs">{m.resource_code}</span>
                    <ul
                      aria-label={m.resource_code}
                      className="relative m-0 h-7 list-none rounded-control border border-line p-0"
                    >
                      {m.windows.length === 0 && <li className="sr-only">{t("noWindows")}</li>}
                      {[...m.windows]
                        .sort(
                          (a, b) => (a.kind === "shift" ? -1 : 0) - (b.kind === "shift" ? -1 : 0),
                        )
                        .map((w) => {
                          const style =
                            STYLE[w.kind === "break" && w.covered ? "covered" : w.kind] ??
                            SHIFT_STYLE;
                          const text = `${label(w)} ${clock(w.start_at)}–${clock(w.end_at)}`;
                          const box = {
                            left: `${(w.start_min / 1440) * 100}%`,
                            width: `${Math.max(((w.end_min - w.start_min) / 1440) * 100, 0.4)}%`,
                          };
                          return (
                            <li key={w.id} className="absolute inset-y-0.5" style={box}>
                              {canEdit && w.kind === "break" ? (
                                <button
                                  type="button"
                                  title={text}
                                  aria-label={`${text}. ${w.covered ? t("markStops") : t("markCovered")}`}
                                  onClick={() => void toggle(w)}
                                  className={`block size-full cursor-pointer rounded-control p-0 focus-visible:outline-1 focus-visible:outline-accent ${style.cls}`}
                                />
                              ) : (
                                <span
                                  title={text}
                                  className={`block size-full rounded-control ${style.cls}`}
                                >
                                  <span className="sr-only">{text}</span>
                                </span>
                              )}
                            </li>
                          );
                        })}
                    </ul>
                  </div>
                ))}
              </div>
            )}
            <ul className="m-0 mt-3 flex list-none flex-wrap gap-4 p-0 text-xs text-muted">
              {(["shift", "break", "covered", "maintenance", "holiday", "overtime"] as const).map(
                (k) => (
                  <li key={k} className="flex items-center gap-1.5">
                    <span
                      aria-hidden="true"
                      className={`inline-block h-3 w-5 rounded-control ${STYLE[k]?.cls ?? ""}`}
                    />
                    {t(`legend.${k}`)}
                  </li>
                ),
              )}
            </ul>
            {c.machines.every((m) => m.windows.length === 0) &&
              c.data_start_at &&
              c.data_end_at && (
                <p className="m-0 mt-2 text-sm text-muted">
                  {t("dataRange", { from: when(c.data_start_at), to: when(c.data_end_at) })}
                </p>
              )}
            {canEdit && <p className="m-0 mt-2 text-xs text-muted">{t("coverHint")}</p>}
          </Panel>
          <Panel label={t("exceptionsLabel")}>
            {c.exceptions.length === 0 ? (
              <p className="m-0 text-sm text-muted">{t("noExceptions")}</p>
            ) : (
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    <th scope="col" className={TH}>
                      {t("when")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("machine")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("kindLabel")}
                    </th>
                    {canEdit && (
                      <th scope="col" className={TH}>
                        {t("action")}
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {c.exceptions.map((e) => (
                    <tr key={e.id} className="border-t border-line">
                      <td className="px-3 py-2 font-mono text-xs">
                        {when(e.start_at)} – {when(e.end_at)}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">{e.resource_code}</td>
                      <td className="px-3 py-2">
                        <span aria-hidden="true">{STYLE[e.kind]?.glyph}</span> {label(e)}
                      </td>
                      {canEdit && (
                        <td className="px-3 py-1">
                          <Button
                            variant="ghost"
                            aria-label={t("deleteWindow", {
                              what: `${label(e)} ${e.resource_code} ${when(e.start_at)}`,
                            })}
                            onPress={() =>
                              change.mutate(() =>
                                api.DELETE("/plants/{plant_code}/calendar/windows/{window_id}", {
                                  params: { path: { plant_code: c.plant_code, window_id: e.id } },
                                }),
                              )
                            }
                          >
                            {t("delete")}
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
          <Panel label={t("overtimeLabel")}>
            {canEdit && (
              <div className="mb-3">
                <FormDialog
                  label={t("addOvertime")}
                  title={t("addOvertime")}
                  submitLabel={t("save")}
                  cancelLabel={t("cancel")}
                  error={error}
                  onSubmit={async (form) => {
                    const { response, error } = await api.PUT("/plants/{plant_code}/overtime", {
                      params: { path: { plant_code: c.plant_code } },
                      body: {
                        resource_code: String(form.get("machine") ?? ""),
                        iso_year: Number(form.get("year")),
                        iso_week: Number(form.get("week")),
                        overtime_h: Number(String(form.get("hours") ?? "").replace(",", ".")),
                      },
                    });
                    if (!response.ok)
                      return (setError(problemOf(error, response.status).message), false);
                    setError(null);
                    await refresh();
                    return true;
                  }}
                >
                  <Field label={t("machine")}>
                    {(id) => (
                      <select id={id} name="machine" className={FIELD}>
                        {c.machines.map((m) => (
                          <option key={m.resource_code} value={m.resource_code}>
                            {m.resource_code} · {m.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </Field>
                  <div className="grid grid-cols-3 gap-3">
                    <Field label={t("year")}>
                      {(id) => (
                        <input
                          id={id}
                          name="year"
                          type="number"
                          min={2000}
                          max={2100}
                          required
                          defaultValue={shown.slice(0, 4)}
                          className={FIELD}
                        />
                      )}
                    </Field>
                    <Field label={t("week")}>
                      {(id) => (
                        <input
                          id={id}
                          name="week"
                          type="number"
                          min={1}
                          max={53}
                          required
                          className={FIELD}
                        />
                      )}
                    </Field>
                    <Field label={t("hours")}>
                      {(id) => (
                        <input
                          id={id}
                          name="hours"
                          inputMode="decimal"
                          required
                          className={FIELD}
                        />
                      )}
                    </Field>
                  </div>
                </FormDialog>
              </div>
            )}
            {c.overtime.length === 0 ? (
              <p className="m-0 text-sm text-muted">{t("noOvertime")}</p>
            ) : (
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    <th scope="col" className={TH}>
                      {t("isoWeek")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("machine")}
                    </th>
                    <th scope="col" className={TH}>
                      {t("hours")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {c.overtime.map((o) => (
                    <tr
                      key={`${o.resource_code}/${o.iso_year}/${o.iso_week}`}
                      className="border-t border-line"
                    >
                      <td data-raw="" className="px-3 py-2 font-mono text-xs">
                        {o.iso_year}-W{String(o.iso_week).padStart(2, "0")}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">{o.resource_code}</td>
                      <td className="px-3 py-2 text-xs">
                        <Count
                          kind="given"
                          value={o.overtime_h}
                          label={`${o.resource_code} · ${o.iso_year}-W${o.iso_week}`}
                          format={(h) => `${h} h`}
                          source={{ what: tf("src.overtime") }}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="m-0 mt-2 text-xs text-muted">{t("overtimeNote")}</p>
          </Panel>
        </>
      )}
    </div>
  );
}
