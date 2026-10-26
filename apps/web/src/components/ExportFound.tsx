"use client";

import { useMutation } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Panel } from "@cip/ui";
import { api, problemOf } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Count } from "./Figure";

type Recognised = components["schemas"]["RecognisedOut"];
type Table = components["schemas"]["TableOut"];
type Role = NonNullable<Table["role"]>;

const ROLES: Role[] = [
  "events",
  "hour_bookings",
  "steps",
  "calendar",
  "orders",
  "products",
  "routings",
  "teams",
  "team_shifts",
  "overtime",
  "capacity_costs",
  "changeovers",
  "outsourcing",
];
const MINIMUM_ROLES: Role[] = ["events", "hour_bookings", "steps", "calendar"];

/**
 * What the app found in the upload (ADR-0011 §2): each table's role and how sure, the three a
 * diagnostic needs, how the tables link, and what was not read. The client names or skips a
 * table; nothing is guessed silently.
 */
export function ExportFound({
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
  const t = useTranslations("import.found");
  const tf = useTranslations("figure");
  const answer = useMutation({
    mutationFn: async (body: { table: string; role: Role | "skip" }) => {
      const { data, error, response } = await api.PUT("/imports/{import_id}/tables", {
        params: { path: { import_id: importId } },
        body,
      });
      if (!data) throw new Error(problemOf(error, response.status).message);
      return data;
    },
    onSuccess: onChanged,
  });
  const readable = found.tables.filter((tb) => tb.problem === null);
  const files = new Set(found.tables.map((tb) => tb.file)).size;
  const extras = readable.filter((tb) => tb.role !== null && !MINIMUM_ROLES.includes(tb.role));

  const sure = (tb: Table) =>
    tb.skipped ? t("skipped") : tb.sure ? t(`sure.${tb.sure}`) : t("notPlaced");

  return (
    <Panel
      label={t("label")}
      status={<span>{t("summary", { tables: readable.length, files })}</span>}
    >
      <div className="flex flex-col gap-4 text-sm">
        <section aria-label={t("minimumLabel")}>
          <h3 className="m-0 mb-1.5 text-xs font-medium tracking-[0.08em] text-muted uppercase">
            {t("minimumLabel")}
          </h3>
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
            {found.minimum.map((m) => (
              <li key={m.key} className="flex flex-wrap items-baseline justify-between gap-2">
                <span>
                  <span aria-hidden="true">{m.tables.length > 0 ? "●" : "○"}</span>{" "}
                  {t(`minimum.${m.key}`)}
                </span>
                <span className={m.tables.length > 0 ? "text-muted" : ""}>
                  {m.tables.length > 0 ? (
                    <>
                      {t("foundIn")}{" "}
                      <span className="font-mono text-xs">{m.tables.join(", ")}</span>
                    </>
                  ) : (
                    t(`missing.${m.key}`)
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>

        {found.to_answer.length > 0 && (
          <p role="status" className="m-0 border-l-2 border-warn pl-3">
            {t("toAnswer", { count: found.to_answer.length })}
          </p>
        )}

        <table className="w-full border-collapse">
          <caption className="sr-only">{t("tablesCaption")}</caption>
          <thead>
            <tr className="text-left text-xs text-muted">
              <th scope="col" className="py-1.5 pr-3 font-normal">
                {t("colTable")}
              </th>
              <th scope="col" className="py-1.5 pr-3 font-normal">
                {t("colWhat")}
              </th>
              <th scope="col" className="py-1.5 pr-3 font-normal">
                {t("colSure")}
              </th>
              <th scope="col" className="py-1.5 pr-3 font-normal">
                {t("colRows")}
              </th>
            </tr>
          </thead>
          <tbody>
            {found.tables.map((tb) => (
              <tr key={tb.table} className="border-t border-line align-top">
                <td className="py-2 pr-3 font-mono text-xs">{tb.table}</td>
                <td className="py-2 pr-3">
                  {tb.problem ? (
                    <span className="text-bad">{t(`problem.${tb.problem}`)}</span>
                  ) : canAnswer ? (
                    <label className="flex flex-col gap-1">
                      <span className="sr-only">{t("whatIs", { table: tb.table })}</span>
                      <select
                        className="rounded-control border border-line-strong bg-surface px-2 py-1 text-sm"
                        value={tb.skipped ? "skip" : (tb.role ?? "")}
                        disabled={answer.isPending}
                        onChange={(e) =>
                          answer.mutate({
                            table: tb.table,
                            role: e.target.value as Role | "skip",
                          })
                        }
                      >
                        {tb.role === null && !tb.skipped && (
                          <option value="" disabled>
                            {t("choose")}
                          </option>
                        )}
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {t(`role.${r}`)}
                          </option>
                        ))}
                        <option value="skip">{t("skip")}</option>
                      </select>
                    </label>
                  ) : (
                    <span>{tb.role ? t(`role.${tb.role}`) : sure(tb)}</span>
                  )}
                  {tb.role && !tb.problem && (
                    <span className="mt-1 block text-xs text-muted">{t(`adds.${tb.role}`)}</span>
                  )}
                  {tb.title_lines > 0 && (
                    <span className="mt-1 block text-xs text-muted">
                      {t("titleLines", { count: tb.title_lines })}
                    </span>
                  )}
                  {tb.totals_lines > 0 && (
                    <span className="mt-1 block text-xs text-muted">
                      {t("totalsLines", { count: tb.totals_lines })}
                    </span>
                  )}
                  {tb.personal_columns > 0 && (
                    <span className="mt-1 block text-xs text-muted">
                      {t("personal", { count: tb.personal_columns })}
                    </span>
                  )}
                </td>
                <td className="py-2 pr-3 text-xs">{tb.problem ? "—" : sure(tb)}</td>
                <td className="py-2 pr-3 text-xs">
                  {tb.problem ? (
                    "—"
                  ) : (
                    <Count
                      value={tb.rows}
                      label={t("rowsLabel", { table: tb.table })}
                      source={{ what: tf("src.found.rows") }}
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {answer.error && (
          <p role="alert" className="m-0 text-bad">
            {answer.error.message}
          </p>
        )}

        {found.links.length > 0 && (
          <section aria-label={t("linksLabel")}>
            <h3 className="m-0 mb-1.5 text-xs font-medium tracking-[0.08em] text-muted uppercase">
              {t("linksLabel")}
            </h3>
            <ul className="m-0 flex list-none flex-col gap-1 p-0 text-xs">
              {found.links.map((l) => (
                <li key={`${l.table}.${l.column}>${l.to_table}.${l.to_column}`}>
                  <span className="font-mono">
                    {l.table} › {l.column}
                  </span>{" "}
                  {t(l.is_list ? "linkList" : "link")}{" "}
                  <span className="font-mono">
                    {l.to_table} › {l.to_column}
                  </span>{" "}
                  <span className="text-muted">
                    ({t("linkFound", { found: l.found, total: l.total })})
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {extras.length === 0 && readable.length > 0 && (
          <p className="m-0 text-xs text-muted">{t("noExtras")}</p>
        )}

        {found.not_read.length > 0 && (
          <section aria-label={t("notReadLabel")}>
            <h3 className="m-0 mb-1.5 text-xs font-medium tracking-[0.08em] text-muted uppercase">
              {t("notReadLabel")}
            </h3>
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {found.not_read.map((n) => (
                <li key={n.name}>
                  <span className="font-mono text-xs">{n.name}</span>: {t(`notRead.${n.problem}`)}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </Panel>
  );
}
