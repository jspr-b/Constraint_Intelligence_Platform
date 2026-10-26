"use client";

import { useMutation } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { Button, Panel } from "@cip/ui";
import { api, problemOf } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { fieldLabel } from "@/lib/model";

type Recognised = components["schemas"]["RecognisedOut"];
type Column = components["schemas"]["FoundColumnOut"];

/**
 * Step 2 of the mapping wizard (ADR-0011 §3): the open questions about columns in plain words,
 * then one summary of what each file is and which columns are used, to confirm. The AI only
 * suggests; its suggestions stay questions until the client says yes.
 */
export function ColumnsFound({
  importId,
  found,
  canAnswer,
  onChanged,
}: {
  importId: string;
  found: Recognised;
  canAnswer: boolean;
  onChanged: () => void;
}) {
  const t = useTranslations("import.columns");
  const tm = useTranslations("model");
  const troles = useTranslations("roles");
  const format = useFormatter();
  const label = (field: string) => fieldLabel(field, tm, tm.has);

  const answer = useMutation({
    mutationFn: async (body: { table: string; column: string; field: string }) => {
      const { data, error, response } = await api.PUT("/imports/{import_id}/columns", {
        params: { path: { import_id: importId } },
        body,
      });
      if (!data) throw new Error(problemOf(error, response.status).message);
      return data;
    },
    onSuccess: onChanged,
  });
  const confirm = useMutation({
    mutationFn: async () => {
      const { data, error, response } = await api.POST("/imports/{import_id}/mapping/confirm", {
        params: { path: { import_id: importId } },
      });
      if (!data) throw new Error(problemOf(error, response.status).message);
      return data;
    },
    onSuccess: onChanged,
  });

  const roleOf = new Map(found.tables.map((tb) => [tb.table, tb.role]));
  const placed = found.tables.filter((tb) => tb.role !== null && tb.problem === null);
  const questions = found.columns.filter((c) => c.question);
  const missing = found.minimum.filter((m) => m.tables.length === 0);
  const blocked =
    found.to_answer.length > 0
      ? t("blocked.tables", { count: found.to_answer.length })
      : questions.length > 0
        ? t("blocked.columns", { count: questions.length })
        : missing.length > 0
          ? t("blocked.minimum")
          : null;

  const choices = (c: Column) => found.fields[roleOf.get(c.table) ?? ""] ?? [];
  const send = (c: Column, field: string) =>
    answer.mutate({ table: c.table, column: c.column, field });

  return (
    <Panel
      label={t("label")}
      status={
        <span>
          {found.confirmed
            ? t("confirmedShort")
            : questions.length > 0
              ? t("questionsShort", { count: questions.length })
              : t("readyShort")}
        </span>
      }
    >
      <div className="flex flex-col gap-4 text-sm">
        <AiBanner state={found.ai.state} canAnswer={canAnswer} />

        {questions.length > 0 && (
          <section aria-label={t("questionsLabel")}>
            <h3 className="m-0 mb-1.5 text-xs font-medium tracking-[0.08em] text-muted uppercase">
              {t("questionsLabel")}
            </h3>
            <p role="status" className="m-0 mb-2 border-l-2 border-warn pl-3">
              {t("questionsIntro", { count: questions.length })}
            </p>
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {questions.map((c) => (
                <Question
                  key={`${c.table}|${c.column}`}
                  column={c}
                  choices={choices(c)}
                  label={label}
                  canAnswer={canAnswer}
                  pending={answer.isPending}
                  onAnswer={(field) => send(c, field)}
                />
              ))}
            </ul>
          </section>
        )}

        <section aria-label={t("summaryLabel")} className="flex flex-col gap-3">
          <h3 className="m-0 text-xs font-medium tracking-[0.08em] text-muted uppercase">
            {t("summaryLabel")}
          </h3>
          {placed.map((tb) => {
            const cols = found.columns.filter((c) => c.table === tb.table);
            return (
              <div key={tb.table} className="border-t border-line pt-2">
                <p className="m-0 mb-1">
                  <span className="font-mono text-xs">{tb.table}</span>
                  {" · "}
                  {tb.role && t(`role.${tb.role}`)}
                </p>
                <table className="w-full border-collapse">
                  <caption className="sr-only">{t("tableCaption", { table: tb.table })}</caption>
                  <thead>
                    <tr className="text-left text-xs text-muted">
                      <th scope="col" className="py-1 pr-3 font-normal">
                        {t("colColumn")}
                      </th>
                      <th scope="col" className="py-1 pr-3 font-normal">
                        {t("colUsedAs")}
                      </th>
                      <th scope="col" className="py-1 pr-3 font-normal">
                        {t("colSure")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {cols.map((c) => (
                      <tr key={c.column} className="border-t border-line align-top">
                        <td className="py-1.5 pr-3 font-mono text-xs">{c.column}</td>
                        <td className="py-1.5 pr-3">
                          {c.personal ? (
                            <span className="text-muted">{t("personal")}</span>
                          ) : canAnswer ? (
                            <label>
                              <span className="sr-only">
                                {t("changeOf", { column: c.column, table: c.table })}
                              </span>
                              <select
                                className="rounded-control border border-line-strong bg-surface px-2 py-1 text-sm"
                                value={c.skipped ? "skip" : (c.fields[0] ?? "")}
                                disabled={answer.isPending}
                                onChange={(e) => send(c, e.target.value)}
                              >
                                {c.fields.length === 0 && !c.skipped && (
                                  <option value="" disabled>
                                    {t("choose")}
                                  </option>
                                )}
                                {choices(c).map((f) => (
                                  <option key={f} value={f}>
                                    {label(f)}
                                  </option>
                                ))}
                                <option value="skip">{t("skip")}</option>
                              </select>
                            </label>
                          ) : (
                            <span>{used(c, label, t)}</span>
                          )}
                          {c.fields.length > 1 && (
                            <span className="mt-1 block text-xs text-muted">
                              {t("alsoFills", { fields: c.fields.slice(1).map(label).join("; ") })}
                            </span>
                          )}
                          {c.part && (
                            <span className="mt-1 block text-xs text-muted">
                              {t(`part.${c.part}`)}
                            </span>
                          )}
                        </td>
                        <td className="py-1.5 pr-3 text-xs">{sureText(c, t)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </section>

        {answer.error && (
          <p role="alert" className="m-0 text-bad">
            {answer.error.message}
          </p>
        )}

        {found.confirmed ? (
          <p className="m-0">
            <span aria-hidden="true">●</span>{" "}
            {t("confirmed", {
              by:
                found.confirmed.by_role && troles.has(found.confirmed.by_role)
                  ? troles(found.confirmed.by_role)
                  : t("someone"),
              at: format.dateTime(new Date(found.confirmed.at), {
                dateStyle: "medium",
                timeStyle: "short",
              }),
            })}
          </p>
        ) : canAnswer ? (
          <div className="flex flex-wrap items-center gap-3">
            <Button
              isDisabled={blocked !== null || confirm.isPending}
              onPress={() => confirm.mutate()}
            >
              {t("confirm")}
            </Button>
            <span className="text-muted">{blocked ?? t("confirmNote")}</span>
          </div>
        ) : (
          <p className="m-0 text-muted">{t("askIt")}</p>
        )}
        {confirm.error && (
          <p role="alert" className="m-0 text-bad">
            {confirm.error.message}
          </p>
        )}
      </div>
    </Panel>
  );
}

type T = ReturnType<typeof useTranslations<"import.columns">>;

function used(c: Column, label: (f: string) => string, t: T): string {
  if (c.skipped) return t("skippedByYou");
  return c.fields[0] ? label(c.fields[0]) : t("notMatched");
}

function sureText(c: Column, t: T): string {
  if (c.personal) return t("sure.personal");
  if (c.skipped) return t("sure.confirmed");
  if (c.source === "ai") return t("sure.ai");
  return c.sure ? t(`sure.${c.sure}`) : t("sure.none");
}

function Question({
  column: c,
  choices,
  label,
  canAnswer,
  pending,
  onAnswer,
}: {
  column: Column;
  choices: string[];
  label: (f: string) => string;
  canAnswer: boolean;
  pending: boolean;
  onAnswer: (field: string) => void;
}) {
  const t = useTranslations("import.columns");
  const suggested = c.fields[0];
  const [choosing, setChoosing] = useState(!suggested);
  return (
    <li className="flex flex-col gap-1.5">
      <p className="m-0">
        {suggested
          ? t("isIt", { column: c.column, table: c.table, field: label(suggested) })
          : t("whatIs", { column: c.column, table: c.table })}
      </p>
      {c.source === "ai" && (
        <p className="m-0 text-xs text-muted">
          <span className="mr-1 rounded-control border border-line-strong px-1.5 py-0.5 text-[10px] tracking-[0.08em] uppercase">
            {t("byAi")}
          </span>
          {c.ai_reason}
        </p>
      )}
      {c.source === "rules" && c.sure === "likely" && (
        <p className="m-0 text-xs text-muted">{t("fromContent")}</p>
      )}
      {canAnswer && (
        <div className="flex flex-wrap items-center gap-2">
          {suggested && !choosing && (
            <>
              <Button
                variant="secondary"
                isDisabled={pending}
                aria-label={t("yesOf", { column: c.column })}
                onPress={() => onAnswer(suggested)}
              >
                {t("yes")}
              </Button>
              <Button
                variant="ghost"
                isDisabled={pending}
                aria-label={t("noOf", { column: c.column })}
                onPress={() => setChoosing(true)}
              >
                {t("noChoose")}
              </Button>
            </>
          )}
          {choosing && (
            <label className="flex items-center gap-2">
              <span className="sr-only">{t("whatIs", { column: c.column, table: c.table })}</span>
              <select
                className="rounded-control border border-line-strong bg-surface px-2 py-1 text-sm"
                defaultValue=""
                disabled={pending}
                onChange={(e) => e.target.value && onAnswer(e.target.value)}
              >
                <option value="" disabled>
                  {t("choose")}
                </option>
                {choices.map((f) => (
                  <option key={f} value={f}>
                    {label(f)}
                  </option>
                ))}
                <option value="skip">{t("skip")}</option>
              </select>
            </label>
          )}
        </div>
      )}
    </li>
  );
}

function AiBanner({ state, canAnswer }: { state: string; canAnswer: boolean }) {
  const t = useTranslations("import.columns.ai");
  if (state === "connected") return null;
  return (
    <p role="note" className="m-0 border-l-2 border-line-strong pl-3 text-muted">
      <span className="font-medium text-text">{t(`${state}.title`)}</span>{" "}
      {state === "not_connected"
        ? t(canAnswer ? "not_connected.it" : "not_connected.other")
        : t(`${state}.body`)}
    </p>
  );
}
