"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { Tab, TabList, TabPanel, Tabs } from "react-aria-components";
import { Button } from "@cip/ui";
import { api } from "@/lib/api/client";
import { Field } from "./FormDialog";

const FIELD =
  "min-h-11 rounded-control border border-line-strong bg-surface px-3 text-sm text-text outline-none focus-visible:outline-1 focus-visible:outline-accent";
const TAB =
  "min-h-10 cursor-pointer border-b-2 border-transparent px-3.5 text-sm text-muted outline-none data-[selected]:border-accent data-[selected]:text-text data-[focus-visible]:outline-1 data-[focus-visible]:outline-accent";

export function LoginForm({ tenantId, ssoError }: { tenantId: string; ssoError: boolean }) {
  const t = useTranslations("login");
  const router = useRouter();
  const queries = useQueryClient();
  const [error, setError] = useState<string | null>(ssoError ? t("ssoFailed") : null);
  const [busy, setBusy] = useState(false);
  const config = useQuery({
    queryKey: ["auth-config", tenantId],
    queryFn: async () =>
      (await api.GET("/auth/config", { params: { query: { tenant_id: tenantId } } })).data ?? null,
  });
  const stations = useQuery({
    queryKey: ["auth-stations", tenantId],
    queryFn: async () =>
      (await api.GET("/auth/stations", { params: { query: { tenant_id: tenantId } } })).data ?? [],
  });

  async function done(target: string) {
    queries.clear();
    router.replace(target);
    router.refresh();
  }

  async function devSignIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = String(new FormData(event.currentTarget).get("email") ?? "");
    setBusy(true);
    const { response } = await api.POST("/auth/dev-login", {
      body: { tenant_id: tenantId, email },
    });
    setBusy(false);
    if (!response.ok) return setError(t("failed"));
    await done("/");
  }

  async function stationSignIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const [plant_code = "", resource_code = ""] = String(form.get("station") ?? "").split("/");
    setBusy(true);
    const { response } = await api.POST("/auth/station-login", {
      body: { tenant_id: tenantId, plant_code, resource_code, pin: String(form.get("pin") ?? "") },
    });
    setBusy(false);
    if (response.status === 403) return setError(t("locked"));
    if (!response.ok) return setError(t("failed"));
    await done("/station");
  }

  const title = config.data?.tenant_name
    ? t("titleTenant", { tenant: config.data.tenant_name })
    : t("title");
  return (
    <section className="flex flex-col gap-5 rounded-panel border border-line bg-surface p-7">
      <h1 className="m-0 text-lg font-medium">{title}</h1>
      {error && (
        <p
          role="alert"
          className="m-0 rounded-control border border-bad px-3 py-2 text-sm text-bad"
        >
          {error}
        </p>
      )}
      <Tabs onSelectionChange={() => setError(null)}>
        <TabList aria-label={t("kind")} className="flex border-b border-line">
          <Tab id="personal" className={TAB}>
            {t("personal")}
          </Tab>
          <Tab id="station" className={TAB}>
            {t("station")}
          </Tab>
        </TabList>
        <TabPanel id="personal" className="flex flex-col gap-3.5 pt-5 outline-none">
          {config.data?.provider === "dev" ? (
            <form onSubmit={devSignIn} className="flex flex-col gap-3.5">
              <Field label={t("email")}>
                {(id) => (
                  <input
                    id={id}
                    name="email"
                    type="email"
                    required
                    autoComplete="username"
                    className={FIELD}
                  />
                )}
              </Field>
              <Button
                type="submit"
                variant="primary"
                isDisabled={busy}
                className="min-h-12 justify-center text-sm"
              >
                {t("devSignIn")}
              </Button>
              <span className="text-xs text-muted">{t("devNote")}</span>
            </form>
          ) : (
            <>
              {/* A full page load to the sign-in route handler; <Link> would prefetch it. */}
              {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
              <a
                href="/auth/oidc/start"
                className="inline-flex min-h-12 items-center justify-center rounded-control border border-accent bg-accent text-sm text-on-accent no-underline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                {t("sso")}
              </a>
              <span className="text-xs text-muted">{t("ssoNote")}</span>
            </>
          )}
        </TabPanel>
        <TabPanel id="station" className="pt-5 outline-none">
          {stations.data && stations.data.length === 0 ? (
            <p className="m-0 text-sm text-muted">{t("noStations")}</p>
          ) : (
            <form onSubmit={stationSignIn} className="flex flex-col gap-3.5">
              <Field label={t("which")}>
                {(id) => (
                  <select id={id} name="station" required className={FIELD}>
                    {(stations.data ?? []).map((s) => (
                      <option
                        key={`${s.plant_code}/${s.resource_code}`}
                        value={`${s.plant_code}/${s.resource_code}`}
                      >
                        {s.resource_code}
                        {s.resource_name ? ` · ${s.resource_name}` : ""}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
              <Field label={t("pin")}>
                {(id) => (
                  <input
                    id={id}
                    name="pin"
                    type="password"
                    inputMode="numeric"
                    pattern="[0-9]{4,8}"
                    minLength={4}
                    maxLength={8}
                    required
                    autoComplete="off"
                    className={`${FIELD} font-mono`}
                  />
                )}
              </Field>
              <Button
                type="submit"
                variant="primary"
                isDisabled={busy}
                className="min-h-12 justify-center text-sm"
              >
                {t("open")}
              </Button>
              <span className="text-xs text-muted">{t("stationNote")}</span>
            </form>
          )}
        </TabPanel>
      </Tabs>
    </section>
  );
}
