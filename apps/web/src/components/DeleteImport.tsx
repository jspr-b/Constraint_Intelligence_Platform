"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { api, problemOf } from "@/lib/api/client";
import { Count } from "./Figure";
import { FIELD, Field, FormDialog } from "./FormDialog";

/** What deleting an import changes, from the engine; nothing changes until Delete (ADR-0010). */
function DeletePreview({ importId, when }: { importId: string; when: (id: string) => string }) {
  const t = useTranslations("import.delete");
  const tl = useTranslations("import.changes.lists");
  const tf = useTranslations("figure");
  const locale = useLocale();
  const preview = useQuery({
    queryKey: ["delete-preview", importId],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/imports/{import_id}/delete-preview", {
        params: { path: { import_id: importId } },
      });
      if (!data) throw new Error(problemOf(error, response.status).message);
      return data;
    },
  });
  const day = (iso: string | null | undefined) =>
    iso ? new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(iso)) : "—";
  const p = preview.data;
  if (preview.isPending)
    return (
      <p role="status" className="m-0 text-sm text-muted">
        {t("working")}
      </p>
    );
  if (!p)
    return (
      <p role="alert" className="m-0 text-sm text-bad">
        {t("failed", { reason: preview.error?.message ?? "" })}
      </p>
    );
  if (!p.in_use) return <p className="m-0 text-sm">{t("notInUse")}</p>;
  const kept = new Set(p.lists_after.map((l) => l.name));
  return (
    <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-sm">
      <li>
        {t("events")}{" "}
        <Count
          value={p.events_removed}
          label={t("eventsRemoved")}
          source={{ what: tf("src.deleteRemoved") }}
        />{" "}
        {t("eventsRemovedText", { after: p.events_after.toLocaleString(locale) })}
      </li>
      <li>
        {t("period", {
          from: `${day(p.period_before[0])} → ${day(p.period_before[1])}`,
          to: p.events_after ? `${day(p.period_after[0])} → ${day(p.period_after[1])}` : "—",
        })}
      </li>
      {p.lists.map((c) => (
        <li key={c.name}>
          {kept.has(c.name)
            ? t("list", { list: tl(c.name as "resources"), before: c.before, after: c.after })
            : t("listGone", { list: tl(c.name as "resources") })}
        </li>
      ))}
      {p.falls_back_to && <li>{t("fallsBack", { when: when(p.falls_back_to) })}</li>}
      {[...new Set(p.lists_after.map((l) => l.from_import_id ?? ""))].map((from) => (
        <li key={from}>
          {t("listsFrom", {
            when: from ? when(from) : "—",
            lists: p.lists_after
              .filter((l) => (l.from_import_id ?? "") === from)
              .map((l) => tl(l.name as "resources"))
              .join(", "),
          })}
        </li>
      ))}
      {p.corrections > 0 && <li>{t("corrections", { count: p.corrections })}</li>}
      {p.imports_left === 0 && <li className="font-medium">{t("empty")}</li>}
    </ul>
  );
}

/** Delete one import of the history, after an in-page confirmation that shows what goes. */
export function DeleteImport({
  importId,
  plant,
  label,
  when,
  onDeleted,
}: {
  importId: string;
  plant: string;
  /** "the upload of Oct 26, 2026, 01:05": names the trigger and the dialog. */
  label: string;
  when: (id: string) => string;
  onDeleted: () => void;
}) {
  const t = useTranslations("import.delete");
  const queries = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  return (
    <FormDialog
      label={t("button")}
      ariaLabel={t("buttonOf", { what: label })}
      variant="ghost"
      title={t("title", { what: label })}
      submitLabel={t("confirm")}
      cancelLabel={t("cancel")}
      error={error}
      onSubmit={async () => {
        const { error: problem, response } = await api.DELETE("/imports/{import_id}", {
          params: { path: { import_id: importId } },
        });
        if (!response.ok) {
          setError(problemOf(problem, response.status).message);
          return false;
        }
        setError(null);
        onDeleted();
        // Not the confirmation itself: the import it asks about is gone.
        queries.removeQueries({ queryKey: ["delete-preview", importId] });
        await queries.invalidateQueries({ queryKey: ["imports", plant] });
        void queries.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "delete-preview" });
        return true;
      }}
    >
      <DeletePreview importId={importId} when={when} />
      <p className="m-0 text-xs text-muted">{t("note")}</p>
    </FormDialog>
  );
}

/** IT only: delete every import, file and row of the plant, with the plant code typed. */
export function DeletePlantData({ plant, onDeleted }: { plant: string; onDeleted: () => void }) {
  const t = useTranslations("import.deletePlant");
  const queries = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  return (
    <details className="rounded-panel border border-line bg-surface p-3 text-sm">
      <summary className="cursor-pointer font-medium">{t("title")}</summary>
      <p className="m-0 mt-2">{t("lead", { plant })}</p>
      <div className="mt-2">
        <FormDialog
          label={t("button", { plant })}
          title={t("dialogTitle", { plant })}
          submitLabel={t("confirm")}
          cancelLabel={t("cancel")}
          error={error}
          onSubmit={async (form) => {
            const { error: problem, response } = await api.DELETE("/plants/{plant_code}/data", {
              params: {
                path: { plant_code: plant },
                query: { confirm: String(form.get("confirm") ?? "") },
              },
            });
            if (!response.ok) {
              setError(problemOf(problem, response.status).message);
              return false;
            }
            setError(null);
            onDeleted();
            await queries.invalidateQueries();
            return true;
          }}
        >
          <p className="m-0 text-sm">{t("warning", { plant })}</p>
          <Field label={t("typeCode", { plant })}>
            {(id) => <input id={id} name="confirm" required autoComplete="off" className={FIELD} />}
          </Field>
        </FormDialog>
      </div>
    </details>
  );
}
