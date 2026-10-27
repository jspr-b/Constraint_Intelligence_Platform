"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Button, Panel } from "@cip/ui";
import { api, problemOf } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Count } from "./Figure";
import { FIELD, Field, FormDialog } from "./FormDialog";
import { ProblemExplanations } from "./ProblemExplanations";
import { ReadOnlyNote } from "./ReadOnlyNote";

type RejectedRow = components["schemas"]["RejectedRowOut"];

const TH = "px-3 py-2 text-left text-[11px] font-medium uppercase tracking-[0.08em] text-muted";
const TD = "px-3 py-2 align-top";
const PAGE = 50;

/** The rows an import rejected, with the rule they break; fix or leave out each one (ADR-0010). */
export function RejectedRows({
  importId,
  plant,
  canFix,
}: {
  importId: string;
  plant: string;
  canFix: boolean;
}) {
  const t = useTranslations("import.rejected");
  const tf = useTranslations("figure");
  const troles = useTranslations("roles");
  const locale = useLocale();
  const queries = useQueryClient();
  const [code, setCode] = useState<string>("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const rows = useQuery({
    queryKey: ["rejected-rows", importId, code, offset],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/imports/{import_id}/rejected-rows", {
        params: {
          path: { import_id: importId },
          query: { offset, limit: PAGE, ...(code ? { code } : {}) },
        },
      });
      if (!data) throw new Error(problemOf(error, response.status).message);
      return data;
    },
  });
  const refresh = () =>
    Promise.all([
      queries.invalidateQueries({ queryKey: ["rejected-rows", importId] }),
      queries.invalidateQueries({ queryKey: ["corrections", plant] }),
      queries.invalidateQueries({ queryKey: ["imports", plant] }),
    ]);
  const undo = useMutation({
    mutationFn: async (id: string) => {
      const { data, error, response } = await api.DELETE("/corrections/{correction_id}", {
        params: { path: { correction_id: id } },
      });
      if (!data) throw new Error(problemOf(error, response.status).message);
      return data;
    },
    onSettled: () => void refresh(),
  });
  const explain = useMutation({
    mutationFn: async () => {
      const { data, error, response } = await api.POST(
        "/imports/{import_id}/rejected-rows/explain",
        { params: { path: { import_id: importId } } },
      );
      if (!data) throw new Error(problemOf(error, response.status).message);
      return data;
    },
    onSettled: () =>
      Promise.all([
        queries.invalidateQueries({ queryKey: ["rejected-rows", importId] }),
        queries.invalidateQueries({ queryKey: ["data-quality", plant] }),
      ]),
  });
  const r = rows.data;
  if (!r || r.total === 0) return null;
  const reason = (row: RejectedRow) =>
    row.code && t.has(`code.${row.code}`)
      ? t(`code.${row.code}`, { example: r.datetime_format })
      : row.reason;
  const save = async (row: RejectedRow, form: FormData): Promise<boolean> => {
    const exclude = form.get("exclude") === "on";
    const { error, response } = await api.POST("/imports/{import_id}/corrections", {
      params: { path: { import_id: importId } },
      body: {
        file: row.file,
        line: row.line,
        column: row.column,
        value: exclude ? null : String(form.get("value") ?? ""),
        exclude,
        reason: String(form.get("reason") ?? ""),
      },
    });
    if (!response.ok) {
      setError(problemOf(error, response.status).message);
      return false;
    }
    setError(null);
    await refresh();
    return true;
  };

  return (
    <Panel
      label={t("label")}
      status={<span>{t("status", { fixed: r.fixed, total: r.total })}</span>}
    >
      <p className="m-0 mb-3 text-sm">
        {t("lead")}{" "}
        <Count value={r.total} label={t("label")} source={{ what: tf("src.rejectedRows") }} />{" "}
        {t("leadRows")}{" "}
        <Count value={r.fixed} label={t("fixedLabel")} source={{ what: tf("src.fixedRows") }} />{" "}
        {t("leadFixed")}
      </p>
      <ProblemExplanations
        codes={r.codes}
        example={r.datetime_format}
        explanations={r.ai_explanations}
        ask={{
          ai: r.ai,
          canAsk: canFix,
          pending: explain.isPending,
          error: explain.error?.message ?? null,
          onAsk: () => explain.mutate(),
        }}
      />
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <Field label={t("filter")}>
          {(id) => (
            <select
              id={id}
              value={code}
              onChange={(e) => {
                setCode(e.target.value);
                setOffset(0);
              }}
              className={FIELD}
            >
              <option value="">{t("all", { count: r.total })}</option>
              {Object.entries(r.codes).map(([c, n]) => (
                <option key={c} value={c}>
                  {t.has(`codeShort.${c}`) ? t(`codeShort.${c}`) : c} ({n})
                </option>
              ))}
            </select>
          )}
        </Field>
        <a
          href={`/api/plants/${encodeURIComponent(plant)}/corrections.csv`}
          className="text-sm text-accent"
          download
        >
          {t("download")}
        </a>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              <th scope="col" className={TH}>
                {t("colFile")}
              </th>
              <th scope="col" className={TH}>
                {t("colLine")}
              </th>
              <th scope="col" className={TH}>
                {t("colColumn")}
              </th>
              <th scope="col" className={TH}>
                {t("colValue")}
              </th>
              <th scope="col" className={TH}>
                {t("colReason")}
              </th>
              <th scope="col" className={TH}>
                {t("colFix")}
              </th>
            </tr>
          </thead>
          <tbody>
            {r.rows.map((row) => {
              const fix = row.correction;
              const where = t("where", { line: row.line, file: row.file });
              return (
                <tr key={`${row.file}:${row.line}`} className="border-t border-line">
                  <td className={`${TD} font-mono text-xs`}>{row.file}</td>
                  <td className={`${TD} font-mono text-xs`}>{row.line}</td>
                  <td className={`${TD} font-mono text-xs`}>{row.column ?? "—"}</td>
                  <td className={`${TD} font-mono text-xs`}>{row.value ?? "—"}</td>
                  <td className={TD}>{reason(row)}</td>
                  <td className={TD}>
                    {fix ? (
                      <div className="flex flex-col gap-1">
                        <span>
                          <span aria-hidden="true">●</span>{" "}
                          {fix.action === "exclude"
                            ? t("leftOut")
                            : t("fixedTo", { value: fix.value ?? "" })}
                        </span>
                        <span className="text-xs text-muted">
                          {t("why", {
                            reason: fix.reason,
                            role: troles.has(fix.role) ? troles(fix.role) : fix.role,
                            when: new Intl.DateTimeFormat(locale, {
                              dateStyle: "medium",
                              timeStyle: "short",
                              hourCycle: "h23",
                            }).format(new Date(fix.created_at)),
                          })}
                        </span>
                        {canFix && (
                          <Button
                            variant="ghost"
                            aria-label={t("undoOf", { where })}
                            onPress={() => undo.mutate(fix.correction_id)}
                            isDisabled={undo.isPending}
                          >
                            {t("undo")}
                          </Button>
                        )}
                      </div>
                    ) : canFix ? (
                      <FormDialog
                        label={t("fix")}
                        ariaLabel={t("fixOf", { where })}
                        variant="ghost"
                        title={t("fixTitle", { where })}
                        submitLabel={t("save")}
                        cancelLabel={t("cancel")}
                        error={error}
                        onSubmit={(form) => save(row, form)}
                      >
                        <p className="m-0 text-sm">
                          {t("uploaded", { column: row.column ?? "—", value: row.value ?? "—" })}{" "}
                          {reason(row)}
                        </p>
                        {row.column && (
                          <Field label={t("newValue", { column: row.column })}>
                            {(id) => (
                              <input
                                id={id}
                                name="value"
                                placeholder={row.code === "not_a_datetime" ? r.datetime_format : ""}
                                className={FIELD}
                              />
                            )}
                          </Field>
                        )}
                        <label className="flex items-center gap-2 text-sm">
                          <input type="checkbox" name="exclude" /> {t("exclude")}
                        </label>
                        <Field label={t("reason")}>
                          {(id) => (
                            <input
                              id={id}
                              name="reason"
                              required
                              placeholder={t("reasonHint")}
                              className={FIELD}
                            />
                          )}
                        </Field>
                        <p className="m-0 text-xs text-muted">{t("fixNote")}</p>
                      </FormDialog>
                    ) : (
                      <span className="text-xs text-muted">{t("notFixed")}</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {undo.error && (
        <p role="alert" className="m-0 mt-2 text-sm text-bad">
          {undo.error.message}
        </p>
      )}
      {r.shown > PAGE && (
        <div className="mt-3 flex items-center gap-3 text-sm">
          <Button
            variant="ghost"
            isDisabled={offset === 0}
            onPress={() => setOffset(Math.max(0, offset - PAGE))}
          >
            {t("previous")}
          </Button>
          <span>
            {t("page", {
              from: offset + 1,
              to: Math.min(offset + PAGE, r.shown),
              total: r.shown,
            })}
          </span>
          <Button
            variant="ghost"
            isDisabled={offset + PAGE >= r.shown}
            onPress={() => setOffset(offset + PAGE)}
          >
            {t("next")}
          </Button>
        </div>
      )}
      {canFix ? (
        <p className="m-0 mt-2 text-xs text-muted">{t("note")}</p>
      ) : (
        <ReadOnlyNote decision="fix_rows" />
      )}
    </Panel>
  );
}
