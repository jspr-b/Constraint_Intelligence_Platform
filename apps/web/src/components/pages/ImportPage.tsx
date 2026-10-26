"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Fragment, useRef, useState } from "react";
import { Tab, TabList, TabPanel, Tabs } from "react-aria-components";
import { Button, Panel } from "@cip/ui";
import { api, problemOf } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Field } from "../FormDialog";
import { conversionLabel, fieldLabel } from "@/lib/model";
import { Count } from "../Figure";
import { ImportChanges, type ImportEvents } from "../ImportChanges";
import { ImportHistory } from "../ImportHistory";
import { ImportPreview } from "../ImportPreview";
import { PageHeader } from "../PageHeader";
import { TechnicalDetails } from "../Problems";
import { ReadOnlyNote } from "../ReadOnlyNote";
import { RejectedRows } from "../RejectedRows";
import { PlantPicker, usePlant } from "../PlantPicker";
import { useView } from "../ViewContext";

type ImportOut = components["schemas"]["ImportOut"];
type FileCheck = components["schemas"]["FileCheckOut"];
type ImportReport = {
  rows_read?: Record<string, number>;
  rows_written?: Record<string, number>;
  row_errors?: { file: string; line: number; reason: string }[];
  dropped_columns?: Record<string, string[]>;
};

const TAB =
  "min-h-10 cursor-pointer border-b-2 border-transparent px-3.5 text-sm text-muted outline-none data-[selected]:border-accent data-[selected]:text-text data-[focus-visible]:outline-1 data-[focus-visible]:outline-accent";
const TH =
  "px-3 py-2 text-left text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted";
const TD = "px-3 py-2 align-top";
const GLYPH: Record<string, string> = {
  ok: "●",
  partial: "◐",
  check: "◐",
  missing: "○",
  "n/a": "·",
};

/** Reason codes from the connector, e.g. "unknown resource code LAS9" -> "unknown". */
function reasonKind(reason: string): string {
  return reason.split(/[ :]/)[0] ?? reason;
}

/** Import page (mockup F4): upload and check files, see how columns map, run, results. */
export function ImportPage() {
  const t = useTranslations("import");
  const tm = useTranslations("model");
  const tf = useTranslations("figure");
  const locale = useLocale();
  const view = useView();
  const queries = useQueryClient();
  const picker = usePlant();
  const { plant } = picker;
  const canRun = (view?.decisions.has("import_run_diagnostic") ?? false) && view?.preview === false;
  const files = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const changeInput = useRef<HTMLInputElement>(null);
  const imports = useQuery({
    queryKey: ["imports", plant],
    enabled: plant !== null,
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/imports", {
          params: { path: { plant_code: plant ?? "" } },
        })
      ).data ?? [],
    refetchInterval: (q) => {
      const last = q.state.data?.[0];
      return last?.status === "running" || last?.facts?.status === "calculating" ? 2000 : false;
    },
  });
  const latest: ImportOut | undefined =
    imports.data?.find((i) => i.import_id === selected) ?? imports.data?.[0];
  const changeable =
    canRun && latest !== undefined && ["uploaded", "failed", "done"].includes(latest.status);
  const refresh = () => queries.invalidateQueries({ queryKey: ["imports", plant] });

  const upload = useMutation({
    mutationFn: async () => {
      const chosen = files.current?.files;
      if (!plant || !chosen || chosen.length === 0) throw new Error("none");
      const form = new FormData();
      for (const f of Array.from(chosen)) form.append("files", f);
      const response = await fetch(`/api/plants/${encodeURIComponent(plant)}/imports`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) {
        const body: unknown = await response.json().catch(() => null);
        throw new Error(problemOf(body, response.status).message);
      }
    },
    onSuccess: () => {
      setError(null);
      setSelected(null);
      if (files.current) files.current.value = "";
      void refresh();
    },
    onError: (e) =>
      setError(
        e.message === "none" ? t("chooseFirst") : e.message ? e.message : t("uploadFailedUnknown"),
      ),
  });
  const run = useMutation({
    mutationFn: async (id: string) => {
      const { response, error } = await api.POST("/imports/{import_id}/run", {
        params: { path: { import_id: id } },
      });
      if (!response.ok) throw new Error(problemOf(error, response.status).message);
    },
    onSuccess: () => void refresh(),
    onError: () => void refresh(),
  });

  const change = useMutation({
    mutationFn: async () => {
      const chosen = changeInput.current?.files;
      if (!latest || !chosen || chosen.length === 0) throw new Error("none");
      const form = new FormData();
      for (const f of Array.from(chosen)) form.append("files", f);
      const response = await fetch(`/api/imports/${latest.import_id}/files`, {
        method: "POST",
        body: form,
      });
      const body: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(problemOf(body, response.status).message);
      return body as ImportOut;
    },
    onSuccess: (changed) => {
      if (changeInput.current) changeInput.current.value = "";
      setSelected(changed.import_id);
      void refresh();
    },
  });
  const remove = useMutation({
    mutationFn: async (name: string) => {
      if (!latest) throw new Error("none");
      const { data, error, response } = await api.DELETE("/imports/{import_id}/files/{name}", {
        params: { path: { import_id: latest.import_id, name } },
      });
      if (!data) throw new Error(problemOf(error, response.status).message);
      return data;
    },
    onSuccess: (changed) => {
      setSelected(changed.import_id);
      void refresh();
    },
  });

  const checks: FileCheck[] = latest?.files ?? [];
  const usable = checks.filter((f) => f.readable && f.recognised_as);
  const ignored = checks.filter((f) => !f.recognised_as);
  const missing = (latest?.needed ?? []).filter(
    (n) => !n.present && !n.in_plant && n.minimum !== false,
  );
  const report = latest?.report?.import as ImportReport | undefined;
  const minimum = latest?.minimum_set ?? [];
  const optional = latest?.optional_set ?? [];
  const checklist = (latest?.report?.checklist ?? []) as {
    number: number;
    data: string;
    need: string;
    status: string;
    detail: string;
  }[];
  const runBlocked = usable.length === 0 ? t("runNoFiles") : null;
  const n = (value: number) => value.toLocaleString(locale);

  /** Run the import, with its state; on the Upload and the Map columns step. */
  const runBar = latest && (
    <>
      {changeable && latest.status !== "running" && latest.facts?.status !== "calculating" && (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            isDisabled={runBlocked !== null}
            onPress={() => run.mutate(latest.import_id)}
          >
            {latest.status === "done" ? t("runAgain") : t("run")}
          </Button>
          <span className="text-xs text-muted">
            {runBlocked ??
              (missing.length > 0
                ? t("runWithGaps", { count: missing.length })
                : t("runExplain", { files: usable.length }))}
          </span>
          {run.error && (
            <p role="alert" className="m-0 w-full text-sm text-bad">
              {run.error.message}
            </p>
          )}
        </div>
      )}
      {latest.status === "running" && (
        <p role="status" className="m-0 text-sm">
          {t("running")}
        </p>
      )}
      {latest.status === "failed" && <ImportFailed latest={latest} />}
      {latest.status === "done" && latest.facts && <FactsState facts={latest.facts} />}
    </>
  );

  const fileStatus = (f: FileCheck) => {
    if (!f.readable) return { glyph: "✕", text: t(`problem.${f.problem ?? "not_text"}`) };
    if (!f.recognised_as) return { glyph: "▲", text: t("notRecognised") };
    return { glyph: "●", text: t("readyToImport") };
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        page="import"
        headline={
          !latest
            ? t("headlineNone")
            : latest.status === "done"
              ? t("headlineDone", {
                  ok: minimum.filter((m) => m.status === "ok").length,
                  total: minimum.length,
                })
              : t(`headline.${latest.status}`)
        }
        actions={<PlantPicker {...picker} />}
      />
      <details open={!latest} className="rounded-panel border border-line bg-surface p-3 text-sm">
        <summary className="cursor-pointer font-medium">{t("howTitle")}</summary>
        <ol className="m-0 mt-2 flex list-decimal flex-col gap-1.5 pl-5">
          <li>{t("how1")}</li>
          <li>{t("how2")}</li>
          <li>{t("how3")}</li>
          <li>{t("how4")}</li>
        </ol>
        <p className="m-0 mt-2 text-muted">{t("howPrivacy")}</p>
      </details>
      {!canRun && <ReadOnlyNote decision="import_run_diagnostic" />}
      {plant && (imports.data?.length ?? 0) > 0 && (
        <ImportHistory
          plant={plant}
          imports={imports.data ?? []}
          shown={latest?.import_id}
          onOpen={setSelected}
        />
      )}
      <Tabs>
        <TabList aria-label={t("steps")} className="flex border-b border-line">
          <Tab id="upload" className={TAB}>
            1 · {t("stepUpload")}
          </Tab>
          <Tab id="map" className={TAB}>
            2 · {t("stepMap")}
          </Tab>
          <Tab id="check" className={TAB}>
            3 · {t("stepCheck")}
          </Tab>
        </TabList>
        <TabPanel id="upload" className="flex flex-col gap-4 pt-4 outline-none">
          {canRun && plant && (
            <Panel label={t("uploadLabel")}>
              <div className="flex flex-wrap items-end gap-3">
                <Field label={t("chooseFiles")}>
                  {(id) => (
                    <input
                      id={id}
                      ref={files}
                      type="file"
                      multiple
                      accept=".csv,.xlsx"
                      className="text-sm text-text file:mr-3 file:rounded-control file:border file:border-line-strong file:bg-surface file:px-3 file:py-1.5 file:text-text"
                    />
                  )}
                </Field>
                <Button
                  variant="primary"
                  onPress={() => upload.mutate()}
                  isDisabled={upload.isPending}
                >
                  {t("upload")}
                </Button>
              </div>
              <p className="m-0 mt-2 text-xs text-muted">{t("uploadNote")}</p>
              {error && (
                <p role="alert" className="m-0 mt-2 text-sm text-bad">
                  {error}
                </p>
              )}
            </Panel>
          )}
          {latest && (
            <Panel label={t("neededLabel")}>
              <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-sm">
                {latest.needed
                  .filter((need) => need.minimum !== false)
                  .map((need) => (
                    <li
                      key={need.key}
                      className="flex flex-wrap items-center justify-between gap-2"
                    >
                      <span>
                        <span aria-hidden="true">
                          {need.present ? "●" : need.in_plant ? "◐" : "○"}
                        </span>{" "}
                        {t(`minimum.${need.key}`)}
                      </span>
                      <span className={need.present || need.in_plant ? "text-muted" : ""}>
                        {need.present
                          ? t("neededPresent")
                          : need.in_plant
                            ? t("neededInPlant")
                            : t("neededMissing", {
                                files: need.sources.map((s) => `${s}.csv`).join(", "),
                              })}
                      </span>
                    </li>
                  ))}
              </ul>
              <p className="m-0 mt-2 text-xs text-muted">{t("neededNote")}</p>
            </Panel>
          )}
          {latest && latest.needed.some((need) => need.minimum === false) && (
            <Panel label={t("optionalLabel")}>
              <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-sm">
                {latest.needed
                  .filter((need) => need.minimum === false)
                  .map((need) => (
                    <li
                      key={need.key}
                      className="flex flex-wrap items-center justify-between gap-2"
                    >
                      <span>
                        <span aria-hidden="true">{need.present ? "●" : "○"}</span>{" "}
                        {t(`minimum.${need.key}`)}{" "}
                        <span className="text-muted">· {t(`adds.${need.key}`)}</span>
                      </span>
                      <span className="text-muted">
                        {need.present
                          ? t("neededPresent")
                          : need.in_plant
                            ? t("neededInPlant")
                            : t("optionalMissing", {
                                files: need.sources.map((s) => `${s}.csv`).join(", "),
                              })}
                      </span>
                    </li>
                  ))}
              </ul>
              <p className="m-0 mt-2 text-xs text-muted">{t("optionalNote")}</p>
            </Panel>
          )}
          <Panel
            label={t("filesLabel")}
            status={latest ? <span>{t(`status.${latest.status}`)}</span> : undefined}
          >
            {!latest ? (
              <p className="m-0 text-sm text-muted">{t("noImport")}</p>
            ) : (
              <div className="flex flex-col gap-3">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr>
                      <th scope="col" className={TH}>
                        {t("colFile")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colRecognised")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colRows")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colColumns")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colFormat")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colStatus")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colPreview")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {checks.map((f) => {
                      const status = fileStatus(f);
                      const isOpen = open === f.name;
                      return (
                        <Fragment key={f.name}>
                          <tr className="border-t border-line">
                            <td className={`${TD} font-mono text-xs`}>{f.name}</td>
                            <td className={TD}>
                              {f.recognised_as ? t(`source.${f.recognised_as}`) : "—"}
                              {f.feeds.length > 0 && (
                                <span className="block text-xs text-muted">
                                  {t("unlocksLabel")}:{" "}
                                  {f.feeds.map((feed) => t(`unlocks.${feed}`)).join("; ")}
                                </span>
                              )}
                            </td>
                            <td className={`${TD} text-xs`}>
                              {f.readable ? (
                                <Count
                                  value={f.rows}
                                  label={`${f.name} · ${t("colRows")}`}
                                  source={{ what: tf("src.upload", { file: f.name }) }}
                                />
                              ) : (
                                "—"
                              )}
                            </td>
                            <td className={`${TD} text-xs`}>
                              {f.readable ? (
                                <Count
                                  value={f.columns}
                                  label={`${f.name} · ${t("colColumns")}`}
                                  source={{ what: tf("src.upload", { file: f.name }) }}
                                />
                              ) : (
                                "—"
                              )}
                              {f.personal_columns.length > 0 && (
                                <span className="block text-muted">
                                  {t("personalDropped", { count: f.personal_columns.length })}
                                </span>
                              )}
                            </td>
                            <td className={`${TD} whitespace-nowrap font-mono text-xs text-muted`}>
                              {f.encoding === "xlsx"
                                ? "Excel"
                                : f.readable
                                  ? `${f.delimiter === "\t" ? "tab" : f.delimiter} · ${f.encoding}`
                                  : "—"}
                            </td>
                            <td className={TD}>
                              <span aria-hidden="true">{status.glyph}</span> {status.text}
                            </td>
                            <td className={`${TD} whitespace-nowrap`}>
                              {changeable && checks.length > 1 && (
                                <Button
                                  variant="ghost"
                                  aria-label={t("changeFiles.removeOf", { file: f.name })}
                                  isDisabled={remove.isPending}
                                  onPress={() => remove.mutate(f.name)}
                                >
                                  {t("changeFiles.remove")}
                                </Button>
                              )}
                              {f.readable && f.preview.length > 0 && (
                                <Button
                                  variant="ghost"
                                  aria-expanded={isOpen}
                                  aria-label={t(isOpen ? "hidePreviewOf" : "showPreviewOf", {
                                    file: f.name,
                                  })}
                                  onPress={() => setOpen(isOpen ? null : f.name)}
                                >
                                  {isOpen ? t("hidePreview") : t("showPreview")}
                                </Button>
                              )}
                            </td>
                          </tr>
                          {isOpen && (
                            <tr>
                              <td colSpan={7} className="bg-raised p-2">
                                <table
                                  aria-label={t("previewOf", { file: f.name })}
                                  className="w-full border-collapse font-mono text-xs"
                                >
                                  <thead>
                                    <tr>
                                      {f.header.map((h) => (
                                        <th
                                          key={h}
                                          scope="col"
                                          className="px-2 py-1 text-left font-medium"
                                        >
                                          {h}
                                          {f.personal_columns.includes(h) && (
                                            <span className="block font-sans font-normal text-muted">
                                              {t("notImported")}
                                            </span>
                                          )}
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody data-raw="">
                                    {f.preview.map((row, i) => (
                                      <tr key={i} className="border-t border-line">
                                        {f.header.map((h) => (
                                          <td key={h} className="px-2 py-1">
                                            {f.personal_columns.includes(h) ? "—" : (row[h] ?? "")}
                                          </td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                                <p className="m-0 mt-1 font-sans text-xs text-muted">
                                  {t("previewNote", { rows: n(f.rows) })}
                                </p>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
                {changeable && (
                  <div className="flex flex-col gap-2 border-t border-line pt-3">
                    <div className="flex flex-wrap items-end gap-3">
                      <Field label={t("changeFiles.choose")}>
                        {(id) => (
                          <input
                            id={id}
                            ref={changeInput}
                            type="file"
                            multiple
                            accept=".csv,.xlsx"
                            className="text-sm text-text file:mr-3 file:rounded-control file:border file:border-line-strong file:bg-surface file:px-3 file:py-1.5 file:text-text"
                          />
                        )}
                      </Field>
                      <Button onPress={() => change.mutate()} isDisabled={change.isPending}>
                        {t("changeFiles.submit")}
                      </Button>
                    </div>
                    <p className="m-0 text-xs text-muted">
                      {latest.status === "done"
                        ? t("changeFiles.noteAfter")
                        : t("changeFiles.noteBefore")}
                    </p>
                    {(change.error ?? remove.error) && (
                      <p role="alert" className="m-0 text-sm text-bad">
                        {change.error?.message === "none"
                          ? t("chooseFirst")
                          : (change.error ?? remove.error)?.message}
                      </p>
                    )}
                  </div>
                )}
                {!changeable && canRun && ["replaced", "deleted"].includes(latest.status) && (
                  <p className="m-0 text-sm text-muted">
                    {t("changeFiles.readOnly", {
                      status: t(`status.${latest.status}`).toLowerCase(),
                    })}
                  </p>
                )}
                {latest.status === "uploaded" && usable.length > 0 && (
                  <ImportPreview
                    importId={latest.import_id}
                    files={checks.map((f) => `${f.name}:${f.rows}`).join()}
                  />
                )}
                {ignored.length > 0 && (
                  <p className="m-0 text-sm">
                    <span aria-hidden="true">▲</span>{" "}
                    {t("ignoredFiles", {
                      count: ignored.length,
                      expected: latest.expected_files.map((s) => `${s}.csv`).join(", "),
                    })}
                  </p>
                )}
                {runBar}
              </div>
            )}
          </Panel>
        </TabPanel>
        <TabPanel id="map" className="flex flex-col gap-4 pt-4 outline-none">
          {!latest ? (
            <p className="m-0 text-sm text-muted">{t("noImport")}</p>
          ) : (
            latest.sources
              .filter((s) => s.file)
              .map((s) => (
                <Panel
                  key={s.source}
                  label={`${s.file}`}
                  status={<span>{t("mappingName", { name: latest.mapping })}</span>}
                >
                  <table className="w-full border-collapse text-sm">
                    <thead>
                      <tr>
                        <th scope="col" className={TH}>
                          {t("colColumn")}
                        </th>
                        <th scope="col" className={TH}>
                          {t("colExample")}
                        </th>
                        <th scope="col" className={TH}>
                          {t("colMapsTo")}
                        </th>
                        <th scope="col" className={TH}>
                          {t("colConversion")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.columns.map((c) => (
                        <tr key={c.name} className="border-t border-line">
                          <td className="px-3 py-2 font-mono text-xs">{c.name}</td>
                          <td data-raw="" className="px-3 py-2 font-mono text-xs text-muted">
                            {c.example ?? "—"}
                          </td>
                          <td className="px-3 py-2">
                            {c.status === "not_imported" ? (
                              <span>
                                <span aria-hidden="true">▲</span> {t("notImported")}
                              </span>
                            ) : c.status === "unused" ? (
                              <span className="text-muted">{t("unused")}</span>
                            ) : (
                              <span title={c.fields.join(", ")}>
                                {c.fields.map((f) => fieldLabel(f, tm, tm.has)).join(", ")}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-xs text-muted">
                            {c.status === "not_imported"
                              ? t("personalNote")
                              : c.conversions
                                  .map((v) => conversionLabel(v, tm, tm.has))
                                  .join(", ") || "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {s.missing_columns.length > 0 && (
                    <p className="m-0 mt-2 text-sm text-bad">
                      {t("missingColumns", { columns: s.missing_columns.join(", ") })}
                    </p>
                  )}
                </Panel>
              ))
          )}
          {runBar}
        </TabPanel>
        <TabPanel id="check" className="flex flex-col gap-4 pt-4 outline-none">
          {!latest || !["done", "replaced"].includes(latest.status) || !report ? (
            <p className="m-0 text-sm text-muted">{t("checkAfterRun")}</p>
          ) : (
            <>
              {latest.report?.events ? (
                <ImportChanges
                  events={latest.report.events as ImportEvents}
                  replaced={(latest.report.lists_replaced as string[] | undefined) ?? []}
                />
              ) : null}
              <Panel label={t("resultsLabel")}>
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr>
                      <th scope="col" className={TH}>
                        {t("colFile")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colRead")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colImported")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colRejected")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colStatus")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {checks.map((f) => {
                      const source = f.recognised_as;
                      const read = source ? (report.rows_read?.[source] ?? 0) : 0;
                      const errors = (report.row_errors ?? []).filter(
                        (e) => e.file.split(".")[0] === source,
                      );
                      const reasons = new Map<string, number[]>();
                      for (const e of errors) {
                        const kind = reasonKind(e.reason);
                        reasons.set(kind, [...(reasons.get(kind) ?? []), e.line]);
                      }
                      const state =
                        !source || !f.readable
                          ? "skipped"
                          : errors.length > 0
                            ? "partial"
                            : "imported";
                      return (
                        <tr key={f.name} className="border-t border-line">
                          <td className={`${TD} font-mono text-xs`}>{f.name}</td>
                          <td className={`${TD} text-xs`}>
                            {source ? (
                              <Count
                                value={read}
                                label={`${f.name} · ${t("colRead")}`}
                                source={{ what: tf("src.importRead", { file: f.name }) }}
                              />
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className={`${TD} text-xs`}>
                            {source
                              ? f.feeds.map((target) => (
                                  <span key={target} className="mr-2 inline-block">
                                    {tm.has(`tables.${target}`) ? tm(`tables.${target}`) : target}{" "}
                                    <Count
                                      value={report.rows_written?.[target] ?? 0}
                                      label={`${f.name} → ${target}`}
                                      source={{
                                        what: tf("src.importWritten", { file: f.name, target }),
                                      }}
                                    />
                                  </span>
                                ))
                              : "—"}
                          </td>
                          <td className={TD}>
                            <Count
                              value={errors.length}
                              label={`${f.name} · ${t("colRejected")}`}
                              source={{ what: tf("src.importRejected", { file: f.name }) }}
                            />
                            {[...reasons.entries()].map(([kind, lines]) => (
                              <span key={kind} className="block text-xs text-muted">
                                {t("rejectReason", {
                                  reason: kind,
                                  count: lines.length,
                                  lines: lines.slice(0, 5).join(", "),
                                })}
                              </span>
                            ))}
                          </td>
                          <td className={TD}>
                            <span aria-hidden="true">
                              {state === "imported" ? "●" : state === "partial" ? "◐" : "○"}
                            </span>{" "}
                            {t(`result.${state}`)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <p className="m-0 mt-2 text-xs text-muted">{t("resultsNote")}</p>
              </Panel>
              {plant && (
                <RejectedRows
                  importId={latest.import_id}
                  plant={plant}
                  canFix={canRun && latest.status === "done"}
                />
              )}
              <Panel label={t("minimumLabel")}>
                <ul className="m-0 flex list-none flex-col gap-2 p-0">
                  {minimum.map((m) => (
                    <li key={m.key} className="flex items-center justify-between gap-3 text-sm">
                      <span>
                        {t(`minimum.${m.key}`)}{" "}
                        <span data-raw="" className="font-mono text-xs text-muted">
                          #{m.numbers.join(", #")}
                        </span>
                      </span>
                      <span>
                        <span aria-hidden="true">{GLYPH[m.status] ?? "·"}</span>{" "}
                        {t(`itemStatus.${m.status}`)}
                      </span>
                    </li>
                  ))}
                </ul>
              </Panel>
              {optional.length > 0 && (
                <Panel label={t("optionalSetLabel")}>
                  <ul className="m-0 flex list-none flex-col gap-2 p-0">
                    {optional.map((m) => (
                      <li key={m.key} className="flex items-center justify-between gap-3 text-sm">
                        <span>
                          {t(`minimum.${m.key}`)}{" "}
                          <span className="text-muted">· {t(`adds.${m.key}`)}</span>
                        </span>
                        <span>
                          <span aria-hidden="true">{GLYPH[m.status] ?? "·"}</span>{" "}
                          {t(`itemStatus.${m.status}`)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Panel>
              )}
              <Panel label={t("checklistLabel")} status={<span>{t("checklistNote")}</span>}>
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr>
                      <th scope="col" className={TH}>
                        #
                      </th>
                      <th scope="col" className={TH}>
                        {t("colRequirement")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colNeed")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colStatus")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colDetail")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {checklist.map((c) => (
                      <tr key={c.number} className="border-t border-line">
                        <td data-raw="" className={`${TD} font-mono text-xs`}>
                          {c.number}
                        </td>
                        <td className={TD}>{c.data}</td>
                        <td className={`${TD} text-muted`}>{c.need}</td>
                        <td className={TD}>
                          <span aria-hidden="true">{GLYPH[c.status] ?? "·"}</span>{" "}
                          {t(`itemStatus.${c.status}`)}
                        </td>
                        <td className={`${TD} text-xs text-muted`}>{c.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>
              <p className="m-0 text-sm">
                <Link href="/data" className="text-accent">
                  {t("toDataQuality")}
                </Link>
              </p>
            </>
          )}
        </TabPanel>
      </Tabs>
    </div>
  );
}

/** The numbers calculated from a finished import: calculating, ready (with period) or failed. */
function FactsState({ facts }: { facts: NonNullable<ImportOut["facts"]> }) {
  const t = useTranslations("import.facts");
  const locale = useLocale();
  const day = (iso: string | null | undefined) =>
    iso ? new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(iso)) : "";
  if (facts.status === "calculating") {
    return (
      <p role="status" className="m-0 text-sm">
        {t("calculating")}
      </p>
    );
  }
  if (facts.status === "failed") {
    return (
      <div role="alert" className="flex flex-col gap-1 text-sm">
        <p className="m-0 text-bad">{t("failed")}</p>
        {facts.error && <TechnicalDetails lines={[facts.error]} />}
      </div>
    );
  }
  return (
    <p role="status" className="m-0 flex flex-wrap gap-x-3 text-sm">
      {/* Dates, not figures: nothing to explain. */}
      <span data-raw>
        <span aria-hidden="true" className="text-ok">
          ●{" "}
        </span>
        {t("ready", { start: day(facts.period_start_at), end: day(facts.period_end_at) })}
      </span>
      <Link href="/data">{t("next")}</Link>
    </p>
  );
}

/** A failed import: where it stopped, what to do, and the technical reason folded away. */
function ImportFailed({ latest }: { latest: ImportOut }) {
  const t = useTranslations("import");
  return (
    <div role="alert" className="flex flex-col gap-1 text-sm">
      <p className="m-0 text-bad">{t("failed")}</p>
      <p className="m-0">
        {latest.failed_step ? t(`failedStep.${latest.failed_step}`) : t("failedUnknown")}
      </p>
      {latest.error && <TechnicalDetails lines={[latest.error]} />}
    </div>
  );
}
