"use client";

import { useTranslations } from "next-intl";
import { useView } from "./ViewContext";

type Decision =
  | "import_run_diagnostic"
  | "fix_rows"
  | "delete_import"
  | "delete_plant_data"
  | "edit_setup_calendar"
  | "manage_logins"
  | "change_access";

/**
 * Why an action is not offered here, and who can do it (no dead ends). In a role preview the
 * reason is the preview, not the role. Several decisions: the missing ones in one sentence,
 * grouped by the roles that hold them ("Planner, IT / ERP owner can fix rows and delete
 * imports; IT / ERP owner can delete all data of a plant.").
 */
export function ReadOnlyNote({
  decision,
  decisions,
}: {
  decision?: Decision;
  decisions?: Decision[];
}) {
  const t = useTranslations();
  const view = useView();
  if (!view) return null;
  if (view.preview) return <p className="m-0 text-sm text-muted">{t("readOnly.preview")}</p>;
  const missing = [...(decisions ?? []), ...(decision ? [decision] : [])].filter(
    (d) => !view.decisions.has(d),
  );
  if (missing.length === 0) return null;
  const role = t(`roles.${view.role}`);
  const action = (list: Decision[]) => list.map((d) => t(`readOnly.actions.${d}`)).join(", ");
  const groups = new Map<string, Decision[]>();
  for (const d of missing) {
    const who = (view.holders.get(d) ?? []).map((r) => t(`roles.${r}`)).join(", ");
    groups.set(who, [...(groups.get(who) ?? []), d]);
  }
  const whoCan = [...groups]
    .filter(([who]) => who)
    .map(([who, list]) => t("readOnly.whoCanDo", { roles: who, action: action(list) }));
  return (
    <p className="m-0 text-sm text-muted">
      {t("readOnly.notAllowed", { role, action: action(missing) })}{" "}
      {missing.length === 1 && whoCan.length === 1
        ? t("readOnly.whoCan", { roles: [...groups.keys()][0] ?? "" })
        : whoCan.length > 0
          ? `${whoCan.join("; ")}.`
          : null}{" "}
      {whoCan.length < groups.size && t("readOnly.askCoo")}
    </p>
  );
}
