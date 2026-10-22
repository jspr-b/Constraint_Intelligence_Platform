"use client";

import { useTranslations } from "next-intl";
import { useView } from "./ViewContext";

type Decision = "import_run_diagnostic" | "edit_setup_calendar" | "manage_logins" | "change_access";

/**
 * Why an action is not offered here, and who can do it (no dead ends). In a role preview the
 * reason is the preview, not the role.
 */
export function ReadOnlyNote({ decision }: { decision: Decision }) {
  const t = useTranslations();
  const view = useView();
  if (!view) return null;
  if (view.preview) return <p className="m-0 text-sm text-muted">{t("readOnly.preview")}</p>;
  if (view.decisions.has(decision)) return null;
  const holders = view.holders.get(decision) ?? [];
  const role = t(`roles.${view.role}`);
  return (
    <p className="m-0 text-sm text-muted">
      {t("readOnly.notAllowed", { role, action: t(`readOnly.actions.${decision}`) })}{" "}
      {holders.length > 0
        ? t("readOnly.whoCan", { roles: holders.map((r) => t(`roles.${r}`)).join(", ") })
        : t("readOnly.askCoo")}
    </p>
  );
}
