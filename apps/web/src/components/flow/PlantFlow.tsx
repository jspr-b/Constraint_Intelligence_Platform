"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Panel } from "@cip/ui";
import { api } from "@/lib/api/client";
import { Count, Figure } from "../Figure";
import { FlowCanvas } from "./FlowCanvas";

/**
 * The flow found in the plant's data: built by the calculation after every upload, so it is
 * there without a button. Loading, empty and failed states say why and what to do next.
 */
export function PlantFlow({
  plant,
  calculating = false,
}: {
  plant: string;
  calculating?: boolean;
}) {
  const t = useTranslations("flowCanvas");
  const locale = useLocale();
  const flow = useQuery({
    queryKey: ["flow", plant],
    queryFn: async () => {
      const { data, response } = await api.GET("/plants/{plant_code}/flow", {
        params: { path: { plant_code: plant } },
      });
      if (!response.ok || !data) throw new Error(String(response.status));
      return data;
    },
    // Recalculation after a data change: look again until the calculation is ready.
    refetchInterval: (q) =>
      calculating || (q.state.data?.run && !["ready", "failed"].includes(q.state.data.run.status))
        ? 2000
        : false,
  });
  const resources = useQuery({
    queryKey: ["resources", plant],
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/resources", {
          params: { path: { plant_code: plant } },
        })
      ).data ?? [],
  });
  const f = flow.data;
  if (flow.isError || resources.isError) {
    return (
      <Panel label={t("label")}>
        <p role="alert" className="m-0 text-sm">
          {t("loadFailed")}{" "}
          <button
            type="button"
            className="cursor-pointer border-0 bg-transparent p-0 text-accent underline"
            onClick={() => {
              void flow.refetch();
              void resources.refetch();
            }}
          >
            {t("tryAgain")}
          </button>
        </p>
      </Panel>
    );
  }
  if (!f || !resources.data || !resources.isFetchedAfterMount) {
    return (
      <Panel label={t("label")}>
        <p role="status" className="m-0 text-sm text-muted">
          {t("loading")}
        </p>
      </Panel>
    );
  }
  if (f.jobs === 0) {
    return (
      <Panel label={t("label")}>
        <p className="m-0 text-sm">
          {calculating || (f.run && f.run.status !== "ready") ? (
            t("calculating")
          ) : (
            <>
              {t("empty")}{" "}
              <Link href="/import" className="text-accent underline">
                {t("toUpload")}
              </Link>
            </>
          )}
        </p>
      </Panel>
    );
  }
  const period =
    f.period_start_at && f.period_end_at
      ? `${new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(f.period_start_at))} – ${new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(f.period_end_at))}`
      : "";
  const main = f.routes[0];
  return (
    <section className="flex flex-col gap-3" aria-label={t("label")}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="grid gap-1">
          <h2 className="m-0 text-xl font-medium">{t("title")}</h2>
          <p className="m-0 text-sm text-muted">{t("lead", { period })}</p>
        </div>
        <div className="flex flex-wrap gap-5">
          <div>
            <div className="text-micro uppercase tracking-[var(--tracking-micro)] text-muted">
              {t("steps")}
            </div>
            <Count
              size="kpi"
              value={f.steps.length}
              label={t("steps")}
              source={{ what: t("countSource"), href: "/setup", page: t("setupPage") }}
            />
          </div>
          <div>
            <div className="text-micro uppercase tracking-[var(--tracking-micro)] text-muted">
              {t("jobsLabel")}
            </div>
            <Count
              size="kpi"
              value={f.jobs}
              label={t("jobsLabel")}
              source={{ what: t("countSource"), href: "/data", page: t("dataPage") }}
            />
          </div>
          {main && (
            <div title={main.steps.join(" → ")}>
              <div className="text-micro uppercase tracking-[var(--tracking-micro)] text-muted">
                {t("mainRoute")}
              </div>
              <Figure size="kpi" figure={main.share} label={t("mainRoute")} />
            </div>
          )}
        </div>
      </div>
      {calculating && (
        <p role="status" className="m-0 text-sm text-muted">
          {t("recalculating")}
        </p>
      )}
      <FlowCanvas flow={f} resources={resources.data} />
    </section>
  );
}
