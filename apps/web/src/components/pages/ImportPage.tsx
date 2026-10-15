"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { Tab, TabList, TabPanel, Tabs } from "react-aria-components";
import { Button, Panel } from "@cip/ui";
import { api } from "@/lib/api/client";
import { Field } from "../FormDialog";
import type { components } from "@/lib/api/schema";
import { PageHeader } from "../PageHeader";
import { PlantPicker, usePlant } from "../PlantPicker";
import { useView } from "../ViewContext";

type ImportOut = components["schemas"]["ImportOut"];

const TAB =
  "min-h-10 cursor-pointer border-b-2 border-transparent px-3.5 text-sm text-muted outline-none data-[selected]:border-accent data-[selected]:text-text data-[focus-visible]:outline-1 data-[focus-visible]:outline-accent";
const TH =
  "px-3 py-2 text-left text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted";
const GLYPH: Record<string, string> = {
  ok: "●",
  partial: "◐",
  check: "◐",
  missing: "○",
  "n/a": "·",
};

/** Import page (mockup F4): upload exports, see how columns map, run, data checklist. */
export function ImportPage() {
  const t = useTranslations("import");
  const view = useView();
  const queries = useQueryClient();
  const picker = usePlant();
  const { plant } = picker;
  const canRun = (view?.decisions.has("import_run_diagnostic") ?? false) && view?.preview === false;
  const files = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const imports = useQuery({
    queryKey: ["imports", plant],
    enabled: plant !== null,
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/imports", {
          params: { path: { plant_code: plant ?? "" } },
        })
      ).data ?? [],
    refetchInterval: (q) => (q.state.data?.[0]?.status === "running" ? 2000 : false),
  });
  const latest: ImportOut | undefined = imports.data?.[0];
  const refresh = () => queries.invalidateQueries({ queryKey: ["imports", plant] });

  const upload = useMutation({
    mutationFn: async () => {
      const chosen = files.current?.files;
      if (!plant || !chosen || chosen.length === 0) return;
      const form = new FormData();
      for (const f of Array.from(chosen)) form.append("files", f);
      const response = await fetch(`/api/plants/${encodeURIComponent(plant)}/imports`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) throw new Error(String(response.status));
    },
    onSuccess: () => {
      setError(null);
      if (files.current) files.current.value = "";
      void refresh();
    },
    onError: (e) => setError(e.message === "413" ? t("tooLarge") : t("uploadFailed")),
  });
  const run = useMutation({
    mutationFn: async (id: string) =>
      api.POST("/imports/{import_id}/run", { params: { path: { import_id: id } } }),
    onSuccess: () => void refresh(),
  });

  const minimum = latest?.minimum_set ?? [];
  const checklist = (latest?.report?.checklist ?? []) as {
    number: number;
    data: string;
    need: string;
    status: string;
    detail: string;
  }[];
  const report = latest?.report?.import as
    | {
        rows_written: Record<string, number>;
        row_errors: unknown[];
        dropped_columns: Record<string, string[]>;
      }
    | undefined;

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
      {!canRun && <p className="m-0 text-sm text-muted">{t("readOnly")}</p>}
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
              <div className="flex flex-wrap items-center gap-3">
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
                        {t("colTargets")}
                      </th>
                      <th scope="col" className={TH}>
                        {t("colStatus")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {latest.sources.map((s) => (
                      <tr key={s.source} className="border-t border-line">
                        <td className="px-3 py-2 font-mono text-xs">{s.file ?? s.source}</td>
                        <td className="px-3 py-2">{s.targets.join(", ")}</td>
                        <td className="px-3 py-2">
                          {!s.file ? (
                            <span>
                              <span aria-hidden="true">○</span> {t("fileMissing")}
                            </span>
                          ) : !s.readable ? (
                            <span className="text-bad">
                              <span aria-hidden="true">✕</span> {t("unreadable")}
                            </span>
                          ) : report ? (
                            <span>
                              <span aria-hidden="true">●</span>{" "}
                              {t("rowsStored", {
                                rows: s.targets.reduce(
                                  (n, target) => n + (report.rows_written[target] ?? 0),
                                  0,
                                ),
                              })}
                            </span>
                          ) : (
                            <span>
                              <span aria-hidden="true">◐</span> {t("uploaded")}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {canRun && latest.status !== "running" && (
                  <div>
                    <Button variant="primary" onPress={() => run.mutate(latest.import_id)}>
                      {latest.status === "done" ? t("runAgain") : t("run")}
                    </Button>
                  </div>
                )}
                {latest.status === "failed" && (
                  <p role="alert" className="m-0 text-sm text-bad">
                    {t("failed", { reason: latest.error ?? "" })}
                  </p>
                )}
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
                          <td className="px-3 py-2 font-mono text-xs text-muted">
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
                              <span className="font-mono text-xs">{c.fields.join(", ")}</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-xs text-muted">
                            {c.status === "not_imported"
                              ? t("personalNote")
                              : c.conversions.join(", ") || "—"}
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
        </TabPanel>
        <TabPanel id="check" className="flex flex-col gap-4 pt-4 outline-none">
          {latest?.status !== "done" ? (
            <p className="m-0 text-sm text-muted">{t("checkAfterRun")}</p>
          ) : (
            <>
              <Panel label={t("minimumLabel")}>
                <ul className="m-0 flex list-none flex-col gap-2 p-0">
                  {minimum.map((m) => (
                    <li key={m.key} className="flex items-center justify-between gap-3 text-sm">
                      <span>
                        {t(`minimum.${m.key}`)}{" "}
                        <span className="font-mono text-xs text-muted">
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
                        <td className="px-3 py-2 font-mono text-xs">{c.number}</td>
                        <td className="px-3 py-2">{c.data}</td>
                        <td className="px-3 py-2 text-muted">{c.need}</td>
                        <td className="px-3 py-2">
                          <span aria-hidden="true">{GLYPH[c.status] ?? "·"}</span>{" "}
                          {t(`itemStatus.${c.status}`)}
                        </td>
                        <td className="px-3 py-2 text-xs text-muted">{c.detail}</td>
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
