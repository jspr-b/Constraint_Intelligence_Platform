"use client";

import { useMutation } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@cip/ui";
import { Count } from "@/components/Figure";
import { api, problemOf } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Recognised = components["schemas"]["RecognisedOut"];
type Code = components["schemas"]["FoundCodeOut"];
type Formats = components["schemas"]["FormatsOut"];
type Step = components["schemas"]["FoundStepOut"];

const SELECT = "rounded-control border border-line-strong bg-surface px-2 py-1 text-sm";
const HEADING = "m-0 text-xs font-medium tracking-[0.08em] text-muted uppercase";

/**
 * Codes and formats of the mapping wizard (ADR-0011 §4), in the same summary as the columns:
 * what each of the plant's codes means, the steps with their own codes, and how dates and
 * numbers are written. ``part`` renders the open questions or the summary.
 */
export function CodesFound({
  importId,
  found,
  canAnswer,
  part,
  onChanged,
  onSkipColumn,
}: {
  importId: string;
  found: Recognised;
  canAnswer: boolean;
  part: "questions" | "summary";
  onChanged: () => void;
  onSkipColumn: (table: string, column: string) => void;
}) {
  const t = useTranslations("import.columns");
  const answer = useMutation({
    mutationFn: async (
      req:
        | { what: "codes"; body: { target: string; code: string; meaning: string } }
        | { what: "formats"; body: components["schemas"]["FormatAnswer"] }
        | { what: "steps"; body: components["schemas"]["StepAnswer"] },
    ) => {
      const params = { path: { import_id: importId } };
      const { data, error, response } =
        req.what === "codes"
          ? await api.PUT("/imports/{import_id}/codes", { params, body: req.body })
          : req.what === "formats"
            ? await api.PUT("/imports/{import_id}/formats", { params, body: req.body })
            : await api.PUT("/imports/{import_id}/steps", { params, body: req.body });
      if (!data) throw new Error(problemOf(error, response.status).message);
      return data;
    },
    onSuccess: onChanged,
  });
  const meaning = (c: { target: string }, m: string) =>
    t(`meaning.${c.target.replace(".", "_")}.${m}` as never);
  const sendCode = (c: Code, m: string) =>
    answer.mutate({ what: "codes", body: { target: c.target, code: c.code, meaning: m } });
  const pending = answer.isPending;
  const error = answer.error && (
    <p role="alert" className="m-0 text-bad">
      {answer.error.message}
    </p>
  );

  if (part === "questions") {
    const codes = found.codes.filter((c) => c.question);
    const f = found.formats;
    const unreadable = f?.times.filter((x) => x.format === null && x.options.length !== 2) ?? [];
    if (codes.length === 0 && found.format_questions === 0) return null;
    return (
      <div className="flex flex-col gap-3">
        <p role="status" className="m-0 border-l-2 border-warn pl-3">
          {t("codes.questionsIntro", { count: codes.length + found.format_questions })}
        </p>
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {f?.date_order_question && f.date_example && (
            <DateOrderQuestion
              formats={f}
              canAnswer={canAnswer}
              pending={pending}
              onAnswer={(order) => answer.mutate({ what: "formats", body: { date_order: order } })}
            />
          )}
          {f?.decimal_question && (
            <li className="flex flex-col gap-1.5">
              <p className="m-0">{t("formats.decimal")}</p>
              {canAnswer && (
                <div className="flex flex-wrap gap-2">
                  {([",", "."] as const).map((mark) => (
                    <Button
                      key={mark}
                      variant="secondary"
                      isDisabled={pending}
                      onPress={() => answer.mutate({ what: "formats", body: { decimal: mark } })}
                    >
                      {t(mark === "," ? "formats.comma" : "formats.point")}
                    </Button>
                  ))}
                </div>
              )}
            </li>
          )}
          {unreadable.map((x) => (
            <li key={`${x.table}|${x.column}`} className="flex flex-col gap-1.5">
              <p className="m-0">{t("formats.unreadable", { column: x.column, table: x.table })}</p>
              {canAnswer && (
                <div>
                  <Button
                    variant="secondary"
                    isDisabled={pending}
                    onPress={() => onSkipColumn(x.table, x.column)}
                  >
                    {t("formats.skipColumn", { column: x.column })}
                  </Button>
                </div>
              )}
            </li>
          ))}
          {codes.map((c) => (
            <CodeQuestion
              key={`${c.target}|${c.code}`}
              code={c}
              choices={found.meanings[c.target] ?? []}
              meaning={(m) => meaning(c, m)}
              canAnswer={canAnswer}
              pending={pending}
              onAnswer={(m) => sendCode(c, m)}
            />
          ))}
        </ul>
        {error}
      </div>
    );
  }

  const groups = new Map<string, { first: Code; codes: Code[] }>();
  for (const c of found.codes) {
    const key = `${c.table}|${c.column}|${c.target}`;
    const group = groups.get(key) ?? { first: c, codes: [] };
    group.codes.push(c);
    groups.set(key, group);
  }
  return (
    <>
      {groups.size > 0 && (
        <section aria-label={t("codes.label")} className="flex flex-col gap-3">
          <h3 className={HEADING}>{t("codes.label")}</h3>
          <p className="m-0 text-muted">{t("codes.intro")}</p>
          {[...groups.entries()].map(([key, { first, codes }]) => (
            <CodeTable
              key={key}
              first={first}
              codes={codes}
              choices={found.meanings[first.target] ?? []}
              meaning={(m) => meaning(first, m)}
              canAnswer={canAnswer}
              pending={pending}
              onAnswer={sendCode}
            />
          ))}
        </section>
      )}
      {found.steps.length > 0 && (
        <StepsTable
          steps={found.steps}
          canAnswer={canAnswer}
          pending={pending}
          onAnswer={(body) => answer.mutate({ what: "steps", body })}
        />
      )}
      {found.formats && (
        <FormatsSummary
          formats={found.formats}
          canAnswer={canAnswer}
          pending={pending}
          onUnit={(table, column, unit) =>
            answer.mutate({ what: "formats", body: { table, column, unit } })
          }
        />
      )}
      {error}
    </>
  );
}

function CodeQuestion({
  code: c,
  choices,
  meaning,
  canAnswer,
  pending,
  onAnswer,
}: {
  code: Code;
  choices: string[];
  meaning: (m: string) => string;
  canAnswer: boolean;
  pending: boolean;
  onAnswer: (meaning: string) => void;
}) {
  const t = useTranslations("import.columns.codes");
  const tf = useTranslations("figure");
  const [choosing, setChoosing] = useState(c.meaning === null);
  const where = { code: c.code, column: c.column, table: c.table };
  return (
    <li className="flex flex-col gap-1.5">
      <p className="m-0">
        {c.meaning ? t("isIt", { ...where, meaning: meaning(c.meaning) }) : t("whatIs", where)}{" "}
        <span className="text-xs text-muted">
          <Count
            value={c.rows}
            label={t("rowsLabel", { code: c.code, table: c.table })}
            source={{ what: tf("src.found.codeRows") }}
          />{" "}
          {t("rowsWith")}
        </span>
      </p>
      {c.source === "ai" ? (
        <p className="m-0 text-xs text-muted">
          <span className="mr-1 rounded-control border border-line-strong px-1.5 py-0.5 text-[10px] tracking-[0.08em] uppercase">
            {t("sure.ai")}
          </span>
          {c.ai_reason}
        </p>
      ) : (
        <p className="m-0 text-xs text-muted">{t(`why.${c.reasons[0] ?? "not_known"}` as never)}</p>
      )}
      {canAnswer && (
        <div className="flex flex-wrap items-center gap-2">
          {c.meaning && !choosing && (
            <>
              <Button
                variant="secondary"
                isDisabled={pending}
                aria-label={t("yesOf", { code: c.code })}
                onPress={() => onAnswer(c.meaning ?? "")}
              >
                {t("yes")}
              </Button>
              <Button
                variant="ghost"
                isDisabled={pending}
                aria-label={t("noOf", { code: c.code })}
                onPress={() => setChoosing(true)}
              >
                {t("noChoose")}
              </Button>
            </>
          )}
          {choosing && (
            <label className="flex items-center gap-2">
              <span className="sr-only">{t("whatIs", where)}</span>
              <select
                className={SELECT}
                defaultValue=""
                disabled={pending}
                onChange={(e) => e.target.value && onAnswer(e.target.value)}
              >
                <option value="" disabled>
                  {t("choose")}
                </option>
                {choices.map((m) => (
                  <option key={m} value={m}>
                    {meaning(m)}
                  </option>
                ))}
                <option value="skip">{t("leaveOut")}</option>
              </select>
            </label>
          )}
        </div>
      )}
    </li>
  );
}

function CodeTable({
  first,
  codes,
  choices,
  meaning,
  canAnswer,
  pending,
  onAnswer,
}: {
  first: Code;
  codes: Code[];
  choices: string[];
  meaning: (m: string) => string;
  canAnswer: boolean;
  pending: boolean;
  onAnswer: (c: Code, meaning: string) => void;
}) {
  const t = useTranslations("import.columns.codes");
  const tf = useTranslations("figure");
  const { table, column } = first;
  return (
    <div className="border-t border-line pt-2">
      <p className="m-0 mb-1">
        <span className="font-mono text-xs">{table}</span>
        {" · "}
        <span className="font-mono text-xs">{column}</span>
      </p>
      <table className="w-full border-collapse">
        <caption className="sr-only">{t("caption", { table, column })}</caption>
        <thead>
          <tr className="text-left text-xs text-muted">
            <th scope="col" className="py-1 pr-3 font-normal">
              {t("colCode")}
            </th>
            <th scope="col" className="py-1 pr-3 font-normal">
              {t("colMeans")}
            </th>
            <th scope="col" className="py-1 pr-3 text-right font-normal">
              {t("colRows")}
            </th>
            <th scope="col" className="py-1 pr-3 font-normal">
              {t("colSure")}
            </th>
          </tr>
        </thead>
        <tbody>
          {codes.map((c) => (
            <tr key={c.code} className="border-t border-line align-top">
              <td className="py-1.5 pr-3 font-mono text-xs" data-raw>
                {c.code}
              </td>
              <td className="py-1.5 pr-3">
                {canAnswer ? (
                  <label>
                    <span className="sr-only">{t("changeOf", { code: c.code })}</span>
                    <select
                      className={SELECT}
                      value={c.skipped ? "skip" : (c.meaning ?? "")}
                      disabled={pending}
                      onChange={(e) => onAnswer(c, e.target.value)}
                    >
                      {c.meaning === null && !c.skipped && (
                        <option value="" disabled>
                          {t("choose")}
                        </option>
                      )}
                      {choices.map((m) => (
                        <option key={m} value={m}>
                          {meaning(m)}
                        </option>
                      ))}
                      <option value="skip">{t("leaveOut")}</option>
                    </select>
                  </label>
                ) : c.skipped ? (
                  t("leftOut")
                ) : c.meaning ? (
                  meaning(c.meaning)
                ) : (
                  t("sure.none")
                )}
              </td>
              <td className="py-1.5 pr-3 text-right">
                <Count
                  value={c.rows}
                  label={t("rowsLabel", { code: c.code, table })}
                  source={{ what: tf("src.found.codeRows") }}
                />
              </td>
              <td className="py-1.5 pr-3 text-xs">
                {c.skipped
                  ? t("leftOut")
                  : c.source === "ai" && c.sure !== "confirmed"
                    ? t("sure.ai")
                    : c.sure === "sure" || c.sure === "likely" || c.sure === "confirmed"
                      ? t(`sure.${c.sure}`)
                      : t("sure.none")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StepsTable({
  steps,
  canAnswer,
  pending,
  onAnswer,
}: {
  steps: Step[];
  canAnswer: boolean;
  pending: boolean;
  onAnswer: (body: components["schemas"]["StepAnswer"]) => void;
}) {
  const t = useTranslations("import.columns.steps");
  const tm = useTranslations("import.columns.meaning");
  return (
    <section aria-label={t("label")} className="flex flex-col gap-2">
      <h3 className={HEADING}>{t("label")}</h3>
      <p className="m-0 text-muted">{t("intro")}</p>
      <table className="w-full border-collapse">
        <caption className="sr-only">{t("caption")}</caption>
        <thead>
          <tr className="text-left text-xs text-muted">
            <th scope="col" className="py-1 pr-3 font-normal">
              {t("colCode")}
            </th>
            <th scope="col" className="py-1 pr-3 font-normal">
              {t("colName")}
            </th>
            <th scope="col" className="py-1 pr-3 font-normal">
              {t("colKind")}
            </th>
            <th scope="col" className="py-1 pr-3 font-normal">
              {t("colStation")}
            </th>
          </tr>
        </thead>
        <tbody>
          {steps.map((s) => (
            <tr key={s.code} className="border-t border-line align-top">
              <td className="py-1.5 pr-3 font-mono text-xs" data-raw>
                {s.code}
              </td>
              <td className="py-1.5 pr-3">
                {canAnswer ? (
                  <StepName
                    step={s}
                    pending={pending}
                    onSave={(name) => onAnswer({ code: s.code, name })}
                  />
                ) : (
                  (s.name ?? "—")
                )}
              </td>
              <td className="py-1.5 pr-3">
                {canAnswer ? (
                  <label>
                    <span className="sr-only">{t("kindOf", { code: s.code })}</span>
                    <select
                      className={SELECT}
                      value={s.kind ?? ""}
                      disabled={pending}
                      onChange={(e) =>
                        e.target.value &&
                        onAnswer({ code: s.code, kind: e.target.value as "machine" | "manual" })
                      }
                    >
                      {s.kind === null && <option value="">{t("notSaid")}</option>}
                      <option value="machine">{tm("resources_kind.machine")}</option>
                      <option value="manual">{tm("resources_kind.manual")}</option>
                    </select>
                  </label>
                ) : s.kind ? (
                  tm(`resources_kind.${s.kind}`)
                ) : (
                  t("notSaid")
                )}
                {s.changed && <span className="mt-1 block text-xs text-muted">{t("changed")}</span>}
              </td>
              <td className="py-1.5 pr-3" data-raw>
                {s.station ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function StepName({
  step,
  pending,
  onSave,
}: {
  step: Step;
  pending: boolean;
  onSave: (name: string) => void;
}) {
  const t = useTranslations("import.columns.steps");
  const [name, setName] = useState(step.name ?? "");
  const changed = name.trim() !== "" && name.trim() !== (step.name ?? "");
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label>
        <span className="sr-only">{t("nameOf", { code: step.code })}</span>
        <input
          className={SELECT}
          value={name}
          maxLength={80}
          disabled={pending}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && changed && onSave(name.trim())}
        />
      </label>
      {changed && (
        <Button
          variant="secondary"
          isDisabled={pending}
          aria-label={t("saveOf", { code: step.code })}
          onPress={() => onSave(name.trim())}
        >
          {t("save")}
        </Button>
      )}
    </div>
  );
}

/** ``YYYY-MM-DDTHH:MM`` (or a date or a time) in plant time, worded without moving it. */
function useReadAs() {
  const format = useFormatter();
  return (read: string) => {
    const date = /^\d{4}-\d{2}-\d{2}/.exec(read)?.[0] ?? null;
    const time = /\d{2}:\d{2}$/.exec(read)?.[0] ?? null;
    const [y = 2000, m = 1, d = 1] = (date ?? "").split("-").map(Number);
    const [h = 0, mi = 0] = (time ?? "").split(":").map(Number);
    return format.dateTime(new Date(Date.UTC(y, m - 1, d, h, mi)), {
      timeZone: "UTC",
      ...(date ? { day: "numeric", month: "long", year: "numeric" } : {}),
      ...(time ? { hour: "2-digit", minute: "2-digit", hourCycle: "h23" } : {}),
    });
  };
}

function DateOrderQuestion({
  formats: f,
  canAnswer,
  pending,
  onAnswer,
}: {
  formats: Formats;
  canAnswer: boolean;
  pending: boolean;
  onAnswer: (order: "day" | "month") => void;
}) {
  const t = useTranslations("import.columns.formats");
  const readAs = useReadAs();
  const day = f.date_readings.day ? readAs(f.date_readings.day) : "";
  const month = f.date_readings.month ? readAs(f.date_readings.month) : "";
  return (
    <li className="flex flex-col gap-1.5">
      <p className="m-0">
        <span data-raw>{t("dateOrder", { example: f.date_example ?? "", day, month })}</span>
      </p>
      <p className="m-0 text-xs text-muted">{t("dateOrderWhy")}</p>
      {canAnswer && (
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" isDisabled={pending} onPress={() => onAnswer("day")}>
            {day}
          </Button>
          <Button variant="secondary" isDisabled={pending} onPress={() => onAnswer("month")}>
            {month}
          </Button>
        </div>
      )}
    </li>
  );
}

const SEPARATORS: Record<string, string> = {
  ";": "semicolon",
  ",": "comma",
  "\t": "tab",
  "|": "pipe",
};

function FormatsSummary({
  formats: f,
  canAnswer,
  pending,
  onUnit,
}: {
  formats: Formats;
  canAnswer: boolean;
  pending: boolean;
  onUnit: (table: string, column: string, unit: "min" | "h") => void;
}) {
  const t = useTranslations("import.columns.formats");
  const readAs = useReadAs();
  const zone = f.timezone ? (f.timezone.split("/").pop() ?? f.timezone).replace(/_/g, " ") : null;
  const sep = f.delimiter ? SEPARATORS[f.delimiter] : null;
  return (
    <section aria-label={t("label")} className="flex flex-col gap-2">
      <h3 className={HEADING}>{t("label")}</h3>
      <ul className="m-0 flex list-disc flex-col gap-1 pl-5">
        <li>{zone ? t("timezone", { zone }) : t("noTimezone")}</li>
        <li>{t("decimalIs", { mark: t(f.decimal === "," ? "markComma" : "markPoint") })}</li>
        {f.delimiter && (
          <li>
            {t("separator", {
              sep: sep ? t(`sep.${sep}` as never) : t("sep.other", { sep: f.delimiter }),
            })}
          </li>
        )}
        {f.title_lines > 0 && <li>{t("titleLines", { count: f.title_lines })}</li>}
        {f.totals_line && <li>{t("totalsLine")}</li>}
        {f.byte_order_mark && <li>{t("bom")}</li>}
        {f.yes_words.length + f.no_words.length > 0 && (
          <li>
            <span data-raw>
              {f.yes_words.length && f.no_words.length
                ? t("yesNo", { yes: f.yes_words.join(", "), no: f.no_words.join(", ") })
                : f.yes_words.length
                  ? t("yesOnly", { yes: f.yes_words.join(", ") })
                  : t("noOnly", { no: f.no_words.join(", ") })}
            </span>
          </li>
        )}
      </ul>
      {f.times.length > 0 && (
        <table className="w-full border-collapse">
          <caption className="sr-only">{t("timesCaption")}</caption>
          <thead>
            <tr className="text-left text-xs text-muted">
              <th scope="col" className="py-1 pr-3 font-normal">
                {t("colColumn")}
              </th>
              <th scope="col" className="py-1 pr-3 font-normal">
                {t("colExample")}
              </th>
              <th scope="col" className="py-1 pr-3 font-normal">
                {t("colRead")}
              </th>
            </tr>
          </thead>
          <tbody>
            {f.times.map((x) => (
              <tr key={`${x.table}|${x.column}`} className="border-t border-line align-top">
                <td className="py-1.5 pr-3">
                  <span className="font-mono text-xs">{x.table}</span>
                  {" · "}
                  <span className="font-mono text-xs">{x.column}</span>
                </td>
                <td className="py-1.5 pr-3 font-mono text-xs" data-raw>
                  {x.example ?? "—"}
                </td>
                <td className="py-1.5 pr-3">
                  {x.real_dates
                    ? t("realDates")
                    : x.example_read
                      ? readAs(x.example_read)
                      : t("notYet")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {f.units.length > 0 && (
        <table className="w-full border-collapse">
          <caption className="sr-only">{t("unitsCaption")}</caption>
          <thead>
            <tr className="text-left text-xs text-muted">
              <th scope="col" className="py-1 pr-3 font-normal">
                {t("colColumn")}
              </th>
              <th scope="col" className="py-1 pr-3 font-normal">
                {t("colUnit")}
              </th>
              <th scope="col" className="py-1 pr-3 font-normal">
                {t("colSure")}
              </th>
            </tr>
          </thead>
          <tbody>
            {f.units.map((u) => (
              <tr key={`${u.table}|${u.column}`} className="border-t border-line align-top">
                <td className="py-1.5 pr-3">
                  <span className="font-mono text-xs">{u.table}</span>
                  {" · "}
                  <span className="font-mono text-xs">{u.column}</span>
                </td>
                <td className="py-1.5 pr-3">
                  {canAnswer ? (
                    <label>
                      <span className="sr-only">{t("unitOf", { column: u.column })}</span>
                      <select
                        className={SELECT}
                        value={u.unit}
                        disabled={pending}
                        onChange={(e) => onUnit(u.table, u.column, e.target.value as "min" | "h")}
                      >
                        <option value="min">{t("unit.min")}</option>
                        <option value="h">{t("unit.h")}</option>
                      </select>
                    </label>
                  ) : (
                    t(`unit.${u.unit}`)
                  )}
                </td>
                <td className="py-1.5 pr-3 text-xs">{t(`unitSure.${u.sure}` as never)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
