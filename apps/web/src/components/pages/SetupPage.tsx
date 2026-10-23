"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Tab, TabList, TabPanel, Tabs } from "react-aria-components";
import { Panel } from "@cip/ui";
import { api, problemOf } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { FIELD, Field, FormDialog } from "../FormDialog";
import { Count, Figure } from "../Figure";
import { PageHeader } from "../PageHeader";
import { ReadOnlyNote } from "../ReadOnlyNote";
import { PlantPicker, usePlant } from "../PlantPicker";
import { useView } from "../ViewContext";
import { termTags } from "../terms";

type Setup = components["schemas"]["SetupOut"];

const TAB =
  "min-h-10 cursor-pointer border-b-2 border-transparent px-3.5 text-sm text-muted outline-none data-[selected]:border-accent data-[selected]:text-text data-[focus-visible]:outline-1 data-[focus-visible]:outline-accent";
const TH =
  "px-3 py-2 text-left text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted";
const TD = "px-3 py-2";

/** Euro input to integer cents (input parsing, not a calculation). Empty means not known. */
function cents(raw: FormDataEntryValue | null): number | null {
  const text = String(raw ?? "")
    .trim()
    .replace(",", ".");
  if (text === "") return null;
  const value = Number(text);
  return Number.isFinite(value) && value >= 0 ? Math.round(value * 100) : null;
}

/** Plant setup page (mockup F5). Items 1-3 of the input list are entered here at kick-off. */
export function SetupPage() {
  const t = useTranslations("setup");
  const tf = useTranslations("figure");
  const view = useView();
  const queries = useQueryClient();
  const picker = usePlant();
  const { plant, plants } = picker;
  const canEdit = (view?.decisions.has("edit_setup_calendar") ?? false) && view?.preview === false;
  const [error, setError] = useState<string | null>(null);
  const setup = useQuery({
    queryKey: ["setup", plant],
    enabled: plant !== null,
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/setup", {
          params: { path: { plant_code: plant ?? "" } },
        })
      ).data ?? null,
  });
  const s: Setup | null | undefined = setup.data;

  /** Run a save; on success show the server's setup, otherwise a translated error. */
  const save = async (
    call: () => Promise<{ data?: Setup; response: Response; error?: unknown }>,
  ) => {
    const { data, response, error: problem } = await call();
    if (!response.ok || !data) {
      setError(problemOf(problem, response.status).message);
      return false;
    }
    setError(null);
    queries.setQueryData(["setup", data.plant_code], data);
    void queries.invalidateQueries({ queryKey: ["plants"] });
    return true;
  };

  const addPlant = canEdit && (
    <FormDialog
      label={t("addPlant")}
      title={t("addPlant")}
      submitLabel={t("save")}
      cancelLabel={t("cancel")}
      variant={plants && plants.length === 0 ? "primary" : "secondary"}
      error={error}
      onSubmit={(form) =>
        save(() =>
          api.POST("/plants", {
            body: {
              plant_code: String(form.get("code") ?? ""),
              name: String(form.get("name") ?? ""),
              timezone_iana: String(form.get("tz") ?? "Europe/Amsterdam"),
            },
          }),
        )
      }
    >
      <Field label={t("plantCode")}>
        {(id) => <input id={id} name="code" required className={`${FIELD} font-mono uppercase`} />}
      </Field>
      <Field label={t("plantName")}>
        {(id) => <input id={id} name="name" required className={FIELD} />}
      </Field>
      <Field label={t("timezone")}>
        {(id) => (
          <input
            id={id}
            name="tz"
            required
            defaultValue="Europe/Amsterdam"
            className={`${FIELD} font-mono`}
          />
        )}
      </Field>
    </FormDialog>
  );

  if (plants && plants.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader page="setup" headline={t("headlineEmpty")} actions={addPlant || undefined} />
        {!canEdit && <ReadOnlyNote decision="edit_setup_calendar" />}
      </div>
    );
  }

  const machines = s?.stations.flatMap((st) => st.machines) ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        page="setup"
        headline={
          s ? t("headline", { stations: s.stations.length, machines: machines.length }) : undefined
        }
        actions={
          <>
            <PlantPicker {...picker} />
            {addPlant}
          </>
        }
      />
      {!canEdit && <ReadOnlyNote decision="edit_setup_calendar" />}
      {s && (
        <Tabs>
          <TabList aria-label={t("label")} className="flex flex-wrap border-b border-line">
            <Tab id="stations" className={TAB}>
              {t("tabStations")}
            </Tab>
            <Tab id="operations" className={TAB}>
              {t("tabOperations")}
            </Tab>
            <Tab id="products" className={TAB}>
              {t("tabProducts")}
            </Tab>
            <Tab id="families" className={TAB}>
              {t("tabFamilies")}
            </Tab>
            <Tab id="costs" className={TAB}>
              {t("tabCosts")}
            </Tab>
          </TabList>
          <TabPanel id="stations" className="flex flex-col gap-3 pt-4 outline-none">
            {canEdit && (
              <div className="flex flex-wrap gap-2">
                <FormDialog
                  label={t("addStation")}
                  title={t("addStation")}
                  submitLabel={t("save")}
                  cancelLabel={t("cancel")}
                  error={error}
                  onSubmit={(form) =>
                    save(() =>
                      api.PUT("/plants/{plant_code}/stations/{station_code}", {
                        params: {
                          path: {
                            plant_code: s.plant_code,
                            station_code: String(form.get("code") ?? ""),
                          },
                        },
                        body: { name: String(form.get("name") ?? "") },
                      }),
                    )
                  }
                >
                  <Field label={t("stationCode")}>
                    {(id) => (
                      <input
                        id={id}
                        name="code"
                        required
                        className={`${FIELD} font-mono uppercase`}
                      />
                    )}
                  </Field>
                  <Field label={t("stationName")}>
                    {(id) => <input id={id} name="name" required className={FIELD} />}
                  </Field>
                </FormDialog>
                {s.stations.length > 0 && (
                  <FormDialog
                    label={t("addMachine")}
                    title={t("addMachine")}
                    submitLabel={t("save")}
                    cancelLabel={t("cancel")}
                    error={error}
                    onSubmit={(form) =>
                      save(() =>
                        api.PUT("/plants/{plant_code}/resources/{resource_code}", {
                          params: {
                            path: {
                              plant_code: s.plant_code,
                              resource_code: String(form.get("code") ?? ""),
                            },
                          },
                          body: {
                            name: String(form.get("name") ?? ""),
                            station_code: String(form.get("station") ?? ""),
                            kind: form.get("kind") === "manual" ? "manual" : "machine",
                            parallel_units: Number(form.get("units") ?? 1),
                          },
                        }),
                      )
                    }
                  >
                    <Field label={t("machineCode")}>
                      {(id) => (
                        <input
                          id={id}
                          name="code"
                          required
                          className={`${FIELD} font-mono uppercase`}
                        />
                      )}
                    </Field>
                    <Field label={t("machineName")}>
                      {(id) => <input id={id} name="name" required className={FIELD} />}
                    </Field>
                    <Field label={t("stepKind")}>
                      {(id) => (
                        <select id={id} name="kind" defaultValue="machine" className={FIELD}>
                          <option value="machine">{t("kindMachine")}</option>
                          <option value="manual">{t("kindManual")}</option>
                        </select>
                      )}
                    </Field>
                    <Field label={t("station")}>
                      {(id) => (
                        <select id={id} name="station" required className={FIELD}>
                          {s.stations.map((st) => (
                            <option key={st.station_code} value={st.station_code}>
                              {st.station_code} · {st.name}
                            </option>
                          ))}
                        </select>
                      )}
                    </Field>
                    <Field label={t("parallelUnits")}>
                      {(id) => (
                        <input
                          id={id}
                          name="units"
                          type="number"
                          min={1}
                          max={100}
                          defaultValue={1}
                          className={FIELD}
                        />
                      )}
                    </Field>
                  </FormDialog>
                )}
              </div>
            )}
            <Panel label={t("stationsLabel")}>
              {s.stations.length === 0 ? (
                <p className="m-0 text-sm text-muted">{t("noStations")}</p>
              ) : (
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr>
                      <th scope="col" className={TH}>
                        {t("station")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("machines")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("stationScreen")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.stations.map((st) => (
                      <tr key={st.station_code} className="border-t border-line">
                        <td className={TD}>
                          {st.name}{" "}
                          <span className="font-mono text-xs text-muted">{st.station_code}</span>
                        </td>
                        <td className={TD}>
                          {st.machines.length === 0
                            ? "—"
                            : st.machines.map((m) => (
                                <span key={m.resource_code} className="mr-3 inline-block">
                                  <span className="font-mono text-xs">{m.resource_code}</span>{" "}
                                  {m.name}
                                  {m.kind === "manual" && (
                                    <span className="text-muted"> · {t("handmade")}</span>
                                  )}
                                  {m.parallel_units > 1 && (
                                    <span className="text-muted">
                                      {" ×"}
                                      <Count
                                        kind="given"
                                        value={m.parallel_units}
                                        label={`${m.resource_code} · ${tf("units.parallel")}`}
                                        source={{ what: tf("src.setupUnits") }}
                                      />
                                    </span>
                                  )}
                                </span>
                              ))}
                        </td>
                        <td className={TD}>
                          {t("screens", {
                            count: st.machines.filter((m) => m.has_station_login).length,
                          })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
          </TabPanel>
          <TabPanel id="operations" className="pt-4 outline-none">
            <Panel label={t("operationsLabel")}>
              {s.operations.length === 0 ? (
                <p className="m-0 text-sm text-muted">{t("noOperations")}</p>
              ) : (
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr>
                      <th scope="col" className={TH}>
                        {t("machine")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("operation")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("measured")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("erp")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("alternatives")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("usedBy")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.operations.map((o) => (
                      <tr
                        key={`${o.resource_code}/${o.operation}`}
                        className="border-t border-line"
                      >
                        <td className={`${TD} font-mono text-xs`}>{o.resource_code}</td>
                        <td className={TD}>{o.operation}</td>
                        <td className={TD}>
                          {o.measured_min_per_unit ? (
                            <Figure
                              figure={o.measured_min_per_unit}
                              label={`${o.resource_code} · ${o.operation}`}
                            />
                          ) : (
                            <span className="text-muted">{t("notMeasured")}</span>
                          )}
                        </td>
                        <td className={`${TD} text-xs text-muted`}>
                          {o.erp_min_per_unit === null || o.erp_min_per_unit === undefined ? (
                            "—"
                          ) : (
                            <Count
                              kind="given"
                              value={o.erp_min_per_unit}
                              label={`${o.resource_code} · ${o.operation} · ${t("erp")}`}
                              source={{ what: tf("src.setupErp") }}
                            />
                          )}
                        </td>
                        <td className={`${TD} font-mono text-xs`}>
                          {o.alternatives.join(", ") || "—"}
                        </td>
                        <td className={TD}>{o.used_by.join(", ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="m-0 mt-2 text-xs text-muted">{t("measuredNote")}</p>
            </Panel>
          </TabPanel>
          <TabPanel id="products" className="pt-4 outline-none">
            <Panel label={t("productsLabel")}>
              {s.products.length === 0 ? (
                <p className="m-0 text-sm text-muted">{t("noProducts")}</p>
              ) : (
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr>
                      <th scope="col" className={TH}>
                        {t("product")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("family")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("price")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("variableCost")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("throughput")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.products.map((p) => (
                      <tr key={p.sku} className="border-t border-line">
                        <td className={TD}>
                          <span className="font-mono text-xs">{p.sku}</span> {p.name}
                        </td>
                        <td className={TD}>{p.family}</td>
                        <td className={`${TD} text-xs`}>
                          <Given
                            cents={p.sales_price_eur_cents}
                            label={`${p.sku} · ${t("price")}`}
                            what={tf("src.setupPrice")}
                          />
                        </td>
                        <td className={`${TD} text-xs`}>
                          <Given
                            cents={p.truly_variable_cost_eur_cents}
                            label={`${p.sku} · ${t("variableCost")}`}
                            what={tf("src.setupPrice")}
                          />
                        </td>
                        <td className={TD}>
                          <Figure
                            figure={p.throughput_per_unit}
                            label={`${p.sku} · ${t("throughput")}`}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="m-0 mt-2 text-xs text-muted">{t.rich("throughputNote", termTags)}</p>
            </Panel>
          </TabPanel>
          <TabPanel id="families" className="flex flex-col gap-3 pt-4 outline-none">
            {canEdit && machines.length > 0 && (
              <div>
                <FormDialog
                  label={t("addChangeover")}
                  title={t("addChangeover")}
                  submitLabel={t("save")}
                  cancelLabel={t("cancel")}
                  error={error}
                  onSubmit={(form) =>
                    save(() =>
                      api.PUT("/plants/{plant_code}/changeovers", {
                        params: { path: { plant_code: s.plant_code } },
                        body: {
                          resource_code: String(form.get("machine") ?? ""),
                          from_setup_family: String(form.get("from") ?? ""),
                          to_setup_family: String(form.get("to") ?? ""),
                          changeover_min: Number(form.get("min") ?? 0),
                        },
                      }),
                    )
                  }
                >
                  <Field label={t("machine")}>
                    {(id) => (
                      <select id={id} name="machine" className={FIELD}>
                        {machines.map((m) => (
                          <option key={m.resource_code} value={m.resource_code}>
                            {m.resource_code} · {m.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </Field>
                  <Field label={t("fromFamily")}>
                    {(id) => <input id={id} name="from" required className={FIELD} />}
                  </Field>
                  <Field label={t("toFamily")}>
                    {(id) => <input id={id} name="to" required className={FIELD} />}
                  </Field>
                  <Field label={t("changeoverMin")}>
                    {(id) => (
                      <input
                        id={id}
                        name="min"
                        type="number"
                        min={0}
                        step="any"
                        required
                        className={FIELD}
                      />
                    )}
                  </Field>
                </FormDialog>
              </div>
            )}
            <Panel label={t("familiesLabel")}>
              {s.changeovers.length === 0 ? (
                <p className="m-0 text-sm text-muted">{t("noChangeovers")}</p>
              ) : (
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr>
                      <th scope="col" className={TH}>
                        {t("machine")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("fromFamily")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("toFamily")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("changeoverMin")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.changeovers.map((c) => (
                      <tr
                        key={`${c.resource_code}/${c.from_setup_family}/${c.to_setup_family}`}
                        className="border-t border-line"
                      >
                        <td className={`${TD} font-mono text-xs`}>{c.resource_code}</td>
                        <td className={TD}>{c.from_setup_family}</td>
                        <td className={TD}>{c.to_setup_family}</td>
                        <td className={`${TD} text-xs`}>
                          <Count
                            kind="given"
                            value={c.changeover_min}
                            label={`${c.resource_code} · ${c.from_setup_family} → ${c.to_setup_family}`}
                            format={(v) => `${v} min`}
                            source={{ what: tf("src.setupChangeover") }}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
          </TabPanel>
          <TabPanel id="costs" className="pt-4 outline-none">
            <Panel label={t("costsLabel")}>
              {machines.length === 0 ? (
                <p className="m-0 text-sm text-muted">{t("noStations")}</p>
              ) : (
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr>
                      <th scope="col" className={TH}>
                        {t("machine")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("overtimePerH")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("extraShift")}
                      </th>
                      {canEdit && (
                        <th scope="col" className={TH}>
                          {t("action")}
                        </th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {machines.map((m) => {
                      const c = s.capacity_costs.find((x) => x.resource_code === m.resource_code);
                      return (
                        <tr key={m.resource_code} className="border-t border-line">
                          <td className={`${TD} font-mono text-xs`}>{m.resource_code}</td>
                          <td className={`${TD} text-xs`}>
                            <Given
                              cents={c?.overtime_eur_cents_per_h}
                              label={`${m.resource_code} · ${t("overtimePerH")}`}
                              what={tf("src.setupCosts")}
                            />
                          </td>
                          <td className={`${TD} text-xs`}>
                            <Given
                              cents={c?.extra_shift_eur_cents}
                              label={`${m.resource_code} · ${t("extraShift")}`}
                              what={tf("src.setupCosts")}
                            />
                          </td>
                          {canEdit && (
                            <td className="px-3 py-1">
                              <FormDialog
                                label={t("editCosts", { machine: m.resource_code })}
                                title={t("editCosts", { machine: m.resource_code })}
                                submitLabel={t("save")}
                                cancelLabel={t("cancel")}
                                error={error}
                                onSubmit={(form) =>
                                  save(() =>
                                    api.PUT("/plants/{plant_code}/capacity-costs/{resource_code}", {
                                      params: {
                                        path: {
                                          plant_code: s.plant_code,
                                          resource_code: m.resource_code,
                                        },
                                      },
                                      body: {
                                        overtime_eur_cents_per_h: cents(form.get("overtime")),
                                        extra_shift_eur_cents: cents(form.get("shift")),
                                      },
                                    }),
                                  )
                                }
                              >
                                <Field label={t("overtimePerH")}>
                                  {(id) => (
                                    <input
                                      id={id}
                                      name="overtime"
                                      inputMode="decimal"
                                      className={`${FIELD} font-mono`}
                                    />
                                  )}
                                </Field>
                                <Field label={t("extraShift")}>
                                  {(id) => (
                                    <input
                                      id={id}
                                      name="shift"
                                      inputMode="decimal"
                                      className={`${FIELD} font-mono`}
                                    />
                                  )}
                                </Field>
                              </FormDialog>
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
              <p className="m-0 mt-2 text-xs text-muted">{t("costsNote")}</p>
            </Panel>
          </TabPanel>
        </Tabs>
      )}
    </div>
  );
}

/** A euro amount from the client's own data (price, cost): opens where it comes from. */
function Given({
  cents,
  label,
  what,
}: {
  cents: number | null | undefined;
  label: string;
  what: string;
}) {
  const locale = useLocale();
  if (cents === null || cents === undefined) return <>—</>;
  return (
    <Count
      kind="given"
      value={cents}
      label={label}
      source={{ what }}
      format={(v) =>
        new Intl.NumberFormat(locale, { style: "currency", currency: "EUR" }).format(v / 100)
      }
    />
  );
}
