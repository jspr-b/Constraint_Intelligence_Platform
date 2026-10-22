"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button, Panel } from "@cip/ui";
import { api, ensureOk, problemOf } from "@/lib/api/client";
import { ROLES } from "@/lib/pages";
import { FIELD, Field, FormDialog } from "../FormDialog";
import { PageHeader } from "../PageHeader";
import { ReadOnlyNote } from "../ReadOnlyNote";
import { useView } from "../ViewContext";

const STATUS_GLYPH: Record<string, string> = {
  active: "●",
  invited: "◐",
  disabled: "○",
  locked: "✕",
};

/** Users page (mockup F2): accounts and station logins, managed by IT only. */
export function UsersPage() {
  const t = useTranslations("users");
  const tr = useTranslations("roles");
  const view = useView();
  const queries = useQueryClient();
  const canManage = view?.decisions.has("manage_logins") ?? false;
  const accounts = useQuery({
    queryKey: ["users"],
    queryFn: async () => (await api.GET("/users")).data ?? null,
  });
  const provider = useQuery({
    queryKey: ["auth-provider"],
    queryFn: async () => {
      const me = (await api.GET("/auth/me")).data;
      if (!me) return null;
      const config = await api.GET("/auth/config", {
        params: { query: { tenant_id: me.tenant_id } },
      });
      return config.data?.provider ?? null;
    },
  });
  const plants = useQuery({
    queryKey: ["plants"],
    queryFn: async () => (await api.GET("/plants")).data ?? [],
  });
  const [plant, setPlant] = useState<string>("");
  const machines = useQuery({
    queryKey: ["resources", plant],
    enabled: plant !== "",
    queryFn: async () =>
      (await api.GET("/plants/{plant_code}/resources", { params: { path: { plant_code: plant } } }))
        .data ?? [],
  });
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [stationError, setStationError] = useState<string | null>(null);
  const refresh = () => queries.invalidateQueries({ queryKey: ["users"] });

  const toggle = useMutation({
    mutationFn: async (target: { kind: "user" | "station"; id: string; enable: boolean }) => {
      const user = { params: { path: { user_id: target.id } } };
      const station = { params: { path: { login_id: target.id } } };
      if (target.kind === "user" && target.enable)
        await ensureOk(api.POST("/users/{user_id}/enable", user));
      if (target.kind === "user" && !target.enable)
        await ensureOk(api.POST("/users/{user_id}/disable", user));
      if (target.kind === "station" && target.enable)
        await ensureOk(api.POST("/station-logins/{login_id}/enable", station));
      if (target.kind === "station" && !target.enable)
        await ensureOk(api.POST("/station-logins/{login_id}/disable", station));
    },
    onSuccess: refresh,
  });

  const users = accounts.data?.users ?? [];
  const stations = accounts.data?.station_logins ?? [];
  const actionButton = (kind: "user" | "station", id: string, status: string, label: string) =>
    canManage && view?.preview === false ? (
      <Button
        variant="ghost"
        aria-label={`${status === "active" || status === "invited" ? t("disable") : t("enable")} ${label}`}
        onPress={() =>
          toggle.mutate({ kind, id, enable: !(status === "active" || status === "invited") })
        }
      >
        {status === "active" || status === "invited" ? t("disable") : t("enable")}
      </Button>
    ) : null;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        page="users"
        headline={
          accounts.data
            ? t("headline", { people: users.length, stations: stations.length })
            : undefined
        }
        actions={
          canManage ? (
            <>
              <FormDialog
                label={t("invite")}
                title={t("invite")}
                submitLabel={t("inviteSubmit")}
                cancelLabel={t("cancel")}
                variant="primary"
                error={inviteError}
                onSubmit={async (form) => {
                  const plantCode = String(form.get("plant") ?? "");
                  const { response, error } = await api.POST("/users", {
                    body: {
                      email: String(form.get("email") ?? ""),
                      role: String(form.get("role")) as (typeof ROLES)[number],
                      plant_code: plantCode || null,
                    },
                  });
                  if (!response.ok)
                    return (setInviteError(problemOf(error, response.status).message), false);
                  setInviteError(null);
                  await refresh();
                  return true;
                }}
              >
                <SignInHint sso={provider.data === "oidc"} />
                <Field label={t("email")}>
                  {(id) => <input id={id} name="email" type="email" required className={FIELD} />}
                </Field>
                <Field label={t("role")}>
                  {(id) => (
                    <select id={id} name="role" required className={FIELD}>
                      {ROLES.filter((r) => r !== "station").map((r) => (
                        <option key={r} value={r}>
                          {tr(r)}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                <Field label={t("plant")}>
                  {(id) => (
                    <select id={id} name="plant" className={FIELD}>
                      <option value="">{t("allPlants")}</option>
                      {(plants.data ?? []).map((p) => (
                        <option key={p.plant_code} value={p.plant_code}>
                          {p.plant_code} · {p.name}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
              </FormDialog>
              <FormDialog
                label={t("addStation")}
                title={t("addStation")}
                submitLabel={t("addStationSubmit")}
                cancelLabel={t("cancel")}
                error={stationError}
                onSubmit={async (form) => {
                  const [plant_code = "", resource_code = ""] = String(
                    form.get("machine") ?? "",
                  ).split("/");
                  const { response, error } = await api.POST("/station-logins", {
                    body: { plant_code, resource_code, pin: String(form.get("pin") ?? "") },
                  });
                  if (!response.ok)
                    return (setStationError(problemOf(error, response.status).message), false);
                  setStationError(null);
                  await refresh();
                  return true;
                }}
              >
                <Field label={t("plant")}>
                  {(id) => (
                    <select
                      id={id}
                      required
                      value={plant}
                      onChange={(e) => setPlant(e.target.value)}
                      className={FIELD}
                    >
                      <option value="" disabled>
                        {t("choosePlant")}
                      </option>
                      {(plants.data ?? []).map((p) => (
                        <option key={p.plant_code} value={p.plant_code}>
                          {p.plant_code} · {p.name}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                <Field label={t("machine")}>
                  {(id) => (
                    <select id={id} name="machine" required className={FIELD}>
                      {(machines.data ?? []).map((m) => (
                        <option key={m.resource_code} value={`${plant}/${m.resource_code}`}>
                          {m.resource_code} · {m.name}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                {plants.data?.length === 0 ? (
                  <p className="m-0 text-sm text-muted">
                    {t("noPlantForStation")} <Link href="/setup">{t("openSetup")}</Link>
                  </p>
                ) : (
                  plant &&
                  machines.data?.length === 0 && (
                    <p className="m-0 text-sm text-muted">
                      {t("noMachines")} <Link href="/import">{t("openImport")}</Link>
                    </p>
                  )
                )}
                <Field label={t("pin")}>
                  {(id) => (
                    <input
                      id={id}
                      name="pin"
                      type="password"
                      inputMode="numeric"
                      pattern="[0-9]{4,8}"
                      required
                      autoComplete="new-password"
                      className={`${FIELD} font-mono`}
                    />
                  )}
                </Field>
              </FormDialog>
            </>
          ) : undefined
        }
      />
      {(!canManage || view?.preview) && <ReadOnlyNote decision="manage_logins" />}
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Panel
          label={t("accounts")}
          status={
            <span>
              {t("accessNote")}{" "}
              <Link href="/access" className="text-accent">
                {t("accessLink")}
              </Link>
            </span>
          }
        >
          {accounts.isPending ? (
            <p className="m-0 text-sm text-muted">{t("loading")}</p>
          ) : users.length + stations.length === 0 ? (
            <p className="m-0 text-sm text-muted">{t("empty")}</p>
          ) : (
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr>
                  {["account", "type", "role", "status", "action"].map((h) => (
                    <th
                      key={h}
                      scope="col"
                      className="px-3 py-2 text-left text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted"
                    >
                      {t(`col.${h}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.user_id} className="border-t border-line">
                    <td className="px-3 py-2 font-mono text-xs">{u.email}</td>
                    <td className="px-3 py-2">{t("person")}</td>
                    <td className="px-3 py-2">{tr(u.role)}</td>
                    <td className="px-3 py-2">
                      <span aria-hidden="true">{STATUS_GLYPH[u.status] ?? "·"}</span>{" "}
                      {t(`status.${u.status}`)}
                    </td>
                    <td className="px-3 py-1">
                      {actionButton("user", u.user_id, u.status, u.email)}
                    </td>
                  </tr>
                ))}
                {stations.map((s) => (
                  <tr key={s.station_login_id} className="border-t border-line">
                    <td className="px-3 py-2 font-mono text-xs">
                      {s.plant_code} / {s.resource_code}
                    </td>
                    <td className="px-3 py-2">{t("stationType")}</td>
                    <td className="px-3 py-2">{tr("station")}</td>
                    <td className="px-3 py-2">
                      <span aria-hidden="true">{STATUS_GLYPH[s.status] ?? "·"}</span>{" "}
                      {t(`status.${s.status}`)}
                    </td>
                    <td className="px-3 py-1">
                      {actionButton("station", s.station_login_id, s.status, s.resource_code)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
        <div className="flex flex-col gap-4">
          <Panel label={t("sso")}>
            <p className="m-0 text-sm">
              {provider.data === "oidc" ? t("ssoOn") : provider.data === "dev" ? t("ssoOff") : ""}
            </p>
            <p className="m-0 mt-2 text-sm text-muted">
              {provider.data === "oidc" ? t("ssoOnNote") : t("ssoOffNote")}
            </p>
          </Panel>
          <Panel label={t("neverStored")}>
            <p className="m-0 text-sm">{t("neverStoredBody")}</p>
            <p className="m-0 mt-2 text-sm text-muted">{t("neverStoredNote")}</p>
          </Panel>
        </div>
      </div>
    </div>
  );
}

/** How an added person signs in; rendered only inside the open dialog, so `window` exists. */
function SignInHint({ sso }: { sso: boolean }) {
  const t = useTranslations("users");
  return (
    <p className="m-0 text-sm text-muted">
      {t(sso ? "inviteHowSso" : "inviteHowDev", { url: `${window.location.origin}/login` })}
    </p>
  );
}
