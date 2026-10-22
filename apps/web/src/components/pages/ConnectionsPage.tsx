"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Button, Panel } from "@cip/ui";
import { api } from "@/lib/api/client";
import { ROLES } from "@/lib/pages";
import { PageHeader } from "../PageHeader";
import { ReadOnlyNote } from "../ReadOnlyNote";
import { PlantPicker, usePlant } from "../PlantPicker";
import { useView } from "../ViewContext";

const TH =
  "px-3 py-2 text-left text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted";
const TD = "px-3 py-2";
const GLYPH: Record<string, string> = {
  done: "●",
  running: "◐",
  uploaded: "◐",
  failed: "✕",
  none: "–",
};

/** Connections page (mockup F7, IT start page): sources, access and data protection facts. */
export function ConnectionsPage() {
  const t = useTranslations("connections");
  const tr = useTranslations("roles");
  const locale = useLocale();
  const view = useView();
  const queries = useQueryClient();
  const picker = usePlant();
  const { plant } = picker;
  const canRun = (view?.decisions.has("import_run_diagnostic") ?? false) && view?.preview === false;
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
  const accounts = useQuery({
    queryKey: ["users"],
    enabled: view?.pages.has("users") ?? false,
    queryFn: async () => (await api.GET("/users")).data ?? null,
  });
  const meta = useQuery({
    queryKey: ["meta"],
    queryFn: async () => (await api.GET("/meta")).data ?? null,
  });
  const provider = useQuery({
    queryKey: ["auth-provider"],
    queryFn: async () => {
      const me = (await api.GET("/auth/me")).data;
      if (!me) return null;
      return (
        (await api.GET("/auth/config", { params: { query: { tenant_id: me.tenant_id } } })).data
          ?.provider ?? null
      );
    },
  });
  const run = useMutation({
    mutationFn: async (id: string) =>
      api.POST("/imports/{import_id}/run", { params: { path: { import_id: id } } }),
    onSuccess: () => void queries.invalidateQueries({ queryKey: ["imports", plant] }),
  });

  const latest = imports.data?.[0];
  const report = latest?.report?.import as
    { rows_written?: Record<string, number>; row_errors?: unknown[] } | undefined;
  const rows = report?.rows_written
    ? Object.values(report.rows_written).reduce((a, b) => a + b, 0)
    : null;
  const rejected = report?.row_errors?.length ?? 0;
  const status = latest?.status ?? "none";
  const when = (iso: string) =>
    new Intl.DateTimeFormat(locale, {
      dateStyle: "medium",
      timeStyle: "short",
      hourCycle: "h23",
    }).format(new Date(iso));
  const users = accounts.data?.users ?? [];
  const stations = accounts.data?.station_logins ?? [];
  const deployed = meta.data?.env !== undefined && meta.data.env !== "dev";

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        page="conn"
        headline={
          !latest
            ? t("headlineNone")
            : status === "done"
              ? rejected > 0
                ? t("headlineRejected", { rejected })
                : t("headlineOk")
              : t(`headline.${status}`)
        }
        actions={
          <>
            <PlantPicker {...picker} />
            {canRun && latest && status !== "running" && (
              <Button variant="primary" onPress={() => run.mutate(latest.import_id)}>
                {t("runNow")}
              </Button>
            )}
          </>
        }
      />
      {!canRun && <ReadOnlyNote decision="import_run_diagnostic" />}
      <Panel label={t("sourcesLabel")} status={<span>{t("writeBackOff")}</span>}>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              <th scope="col" className={TH}>
                {t("source")}
              </th>
              <th scope="col" className={TH}>
                {t("method")}
              </th>
              <th scope="col" className={TH}>
                {t("schedule")}
              </th>
              <th scope="col" className={TH}>
                {t("lastRun")}
              </th>
              <th scope="col" className={TH}>
                {t("rows")}
              </th>
              <th scope="col" className={TH}>
                {t("status")}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-line">
              <td className={TD}>{t("uploadSource")}</td>
              <td className={TD}>{t("uploadMethod")}</td>
              <td className={TD}>{t("manual")}</td>
              <td className={`${TD} font-mono text-xs`}>
                {latest ? when(latest.created_at) : "—"}
              </td>
              <td className={`${TD} font-mono text-xs`}>
                {rows === null ? "—" : rows.toLocaleString(locale)}
              </td>
              <td className={TD}>
                <span aria-hidden="true">{GLYPH[status]}</span> {t(`importStatus.${status}`)}
                {rejected > 0 && (
                  <>
                    {" · "}
                    <Link href="/import" className="text-accent">
                      {t("rejected", { rejected })}
                    </Link>
                  </>
                )}
              </td>
            </tr>
            <tr className="border-t border-line">
              <td className={TD}>{t("scheduledSource")}</td>
              <td className={TD}>{t("scheduledMethod")}</td>
              <td className={TD}>—</td>
              <td className={TD}>—</td>
              <td className={TD}>—</td>
              <td className={`${TD} text-muted`}>
                <span aria-hidden="true">–</span> {t("notConfigured")}
              </td>
            </tr>
            <tr className="border-t border-line">
              <td className={TD}>{t("gatewaySource")}</td>
              <td className={TD}>{t("gatewayMethod")}</td>
              <td className={TD}>{t("live")}</td>
              <td className={TD}>—</td>
              <td className={TD}>—</td>
              <td className={`${TD} text-muted`}>
                <span aria-hidden="true">–</span> {t("later")}
              </td>
            </tr>
          </tbody>
        </table>
      </Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel label={t("accessLabel")}>
          <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted">{t("sso")}</dt>
            <dd className="m-0">
              {provider.data === "oidc" ? t("ssoOn") : provider.data === "dev" ? t("ssoOff") : "—"}
            </dd>
            <dt className="text-muted">{t("personalLogins")}</dt>
            <dd className="m-0">
              {accounts.data
                ? ROLES.filter((r) => r !== "station")
                    .map(
                      (r) =>
                        `${tr(r)} ${users.filter((u) => u.role === r && u.status !== "disabled").length}`,
                    )
                    .join(" · ")
                : "—"}
            </dd>
            <dt className="text-muted">{t("stationLogins")}</dt>
            <dd className="m-0">
              {accounts.data
                ? t("stationCount", { count: stations.filter((s) => s.status === "active").length })
                : "—"}
            </dd>
          </dl>
          <p className="m-0 mt-3 text-sm">
            <Link href="/users" className="text-accent">
              {t("toUsers")}
            </Link>
          </p>
        </Panel>
        <Panel label={t("protectionLabel")}>
          <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted">{t("region")}</dt>
            <dd className="m-0">{deployed ? t("regionEu") : t("byDeployment")}</dd>
            <dt className="text-muted">{t("encryption")}</dt>
            <dd className="m-0">{deployed ? t("encryptionOn") : t("byDeployment")}</dd>
            <dt className="text-muted">{t("isolation")}</dt>
            <dd className="m-0">{t("isolationValue")}</dd>
            <dt className="text-muted">{t("floorData")}</dt>
            <dd className="m-0">{t("floorDataValue")}</dd>
            <dt className="text-muted">{t("erp")}</dt>
            <dd className="m-0">{t("erpValue")}</dd>
          </dl>
        </Panel>
      </div>
    </div>
  );
}
