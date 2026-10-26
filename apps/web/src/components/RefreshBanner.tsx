"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { LiveDot } from "@cip/ui";
import { DATA_CHANGED, api, problemOf } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import type { View } from "@/lib/session";

type Refresh = components["schemas"]["RefreshOut"];

/** How long "Updated 14:05" stays on the pages after a recalculation finished. */
const RECENT_MS = 15 * 60_000;

/** How long the banner looks closely after a change saved on this page. */
const WATCH_MS = 30_000;

export function useRefreshStatus() {
  const [watchUntil, setWatchUntil] = useState(0);
  const status = useQuery({
    queryKey: ["refresh-status"],
    queryFn: async () => (await api.GET("/refresh-status")).data ?? [],
    refetchInterval: (q) =>
      q.state.data?.some((p) => p.status === "calculating") || q.state.dataUpdatedAt < watchUntil
        ? 2000
        : 30_000,
  });
  const { refetch } = status;
  useEffect(() => {
    const changed = () => {
      setWatchUntil(Date.now() + WATCH_MS);
      void refetch();
    };
    window.addEventListener(DATA_CHANGED, changed);
    return () => window.removeEventListener(DATA_CHANGED, changed);
  }, [refetch]);
  return status;
}

/** Once a plant's numbers are recalculated, every page reads them again without a reload. */
function useReloadWhenReady(plants: Refresh[] | undefined) {
  const queries = useQueryClient();
  const before = useRef(new Map<string, string>());
  useEffect(() => {
    if (!plants) return;
    const finished = plants.some(
      (p) => before.current.get(p.plant_code) === "calculating" && p.status !== "calculating",
    );
    before.current = new Map(plants.map((p) => [p.plant_code, p.status]));
    if (finished)
      void queries.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "refresh-status" });
  }, [plants, queries]);
}

function Retry({ plant }: { plant: string }) {
  const t = useTranslations("refresh");
  const queries = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <>
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          const { error: problem, response } = await api.POST("/plants/{plant_code}/refresh", {
            params: { path: { plant_code: plant } },
          });
          setBusy(false);
          setError(response.ok ? null : problemOf(problem, response.status).message);
          await queries.invalidateQueries({ queryKey: ["refresh-status"] });
        }}
        className="cursor-pointer rounded-control border border-line-strong bg-transparent px-2 py-1 text-sm text-accent disabled:cursor-default disabled:text-faint"
      >
        {t("retry")}
      </button>
      {error && <span className="text-bad">{error}</span>}
    </>
  );
}

function PlantLine({
  p,
  view,
  now,
  single,
}: {
  p: Refresh;
  view: View;
  now: number;
  /** One plant with old data: its own line says so; several share one line. */
  single: boolean;
}) {
  const t = useTranslations("refresh");
  const locale = useLocale();
  const at = (iso: string | null | undefined) =>
    iso
      ? new Intl.DateTimeFormat(locale, {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          hourCycle: "h23",
          timeZone: p.timezone_iana,
        }).format(new Date(iso))
      : "—";
  const day = (iso: string) =>
    new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeZone: p.timezone_iana }).format(
      new Date(iso),
    );
  const plant = p.plant_name;
  const why = p.reason ? t(`reason.${p.reason}`) : t("reason.import");
  const canRetry = view.decisions.has("import_run_diagnostic") && !view.preview;
  const canImport = view.decisions.has("import_run_diagnostic") && !view.preview;
  const lines = [];

  if (p.status === "calculating") {
    lines.push(
      <p key="calc" role="status" className="m-0 flex items-baseline gap-2">
        <span className="shrink-0">
          <LiveDot />
        </span>
        <span>
          {t("calculating", { plant, why, since: at(p.requested_at) })}{" "}
          <span className="text-muted">
            {p.numbers_at ? t("keepsOld", { at: at(p.numbers_at) }) : t("firstTime")}
          </span>
        </span>
      </p>,
    );
  } else if (p.status === "failed") {
    lines.push(
      <div key="failed" role="alert" className="flex flex-wrap items-center gap-2">
        <span>
          <span className="text-bad">✕ {t("failed", { plant, why })}</span>{" "}
          {t(`problem.${p.problem ?? "error"}`)}{" "}
          {p.numbers_at ? t("older", { at: at(p.numbers_at) }) : t("noNumbers")}{" "}
          {!canRetry && t("askIt")}
        </span>
        {canRetry && <Retry plant={p.plant_code} />}
      </div>,
    );
  } else if (
    p.status === "ready" &&
    p.numbers_at &&
    now - new Date(p.numbers_at).getTime() < RECENT_MS
  ) {
    lines.push(
      <p key="ready" role="status" className="m-0">
        ✓ {t("updated", { plant, why, at: at(p.numbers_at) })}
      </p>,
    );
  }
  if (single && isOld(p) && p.last_event_at) {
    lines.push(
      <p key="old" className="m-0 text-muted">
        {t("old", { plant, date: day(p.last_event_at), days: p.data_age_days ?? 0 })}{" "}
        <NewData canImport={canImport} />
      </p>,
    );
  }
  return lines.length ? <>{lines}</> : null;
}

const isOld = (p: Refresh) =>
  p.last_event_at !== null && p.data_age_days !== null && p.data_age_days >= p.old_after_days;

function NewData({ canImport }: { canImport: boolean }) {
  const t = useTranslations("refresh");
  return canImport ? <Link href="/import">{t("upload")}</Link> : <>{t("askExport")}</>;
}

/** Several plants with old data: one line naming them, newest data date each. */
function OldPlants({ plants, view }: { plants: Refresh[]; view: View }) {
  const t = useTranslations("refresh");
  const locale = useLocale();
  const day = (p: Refresh) =>
    new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeZone: p.timezone_iana }).format(
      new Date(p.last_event_at ?? 0),
    );
  return (
    <p className="m-0 text-muted">
      {t("oldMany", {
        days: plants[0]?.old_after_days ?? 7,
        plants: plants.map((p) => t("oldOne", { plant: p.plant_name, date: day(p) })).join("; "),
      })}{" "}
      <NewData canImport={view.decisions.has("import_run_diagnostic") && !view.preview} />
    </p>
  );
}

/** On every page: why the numbers are being recalculated, when they are from, a failed or
 * stuck recalculation with a retry, and how old the data is (ADR-0010 point 10). */
export function RefreshBanner({ view }: { view: View }) {
  const t = useTranslations("refresh");
  const status = useRefreshStatus();
  useReloadWhenReady(status.data);
  const plants = status.data ?? [];
  const busy = plants.some((p) => p.status === "calculating" || p.status === "failed");
  const old = plants.filter(isOld);
  const lines = plants.map((p) => (
    <PlantLine
      key={p.plant_code}
      p={p}
      view={view}
      now={status.dataUpdatedAt}
      single={old.length === 1}
    />
  ));
  if (!plants.length) return null;
  return (
    <section
      aria-label={t("label")}
      className={`mb-4 flex flex-col gap-1 rounded-panel border px-4 py-2 text-sm empty:hidden ${
        busy ? "border-accent" : "border-line"
      }`}
    >
      {lines}
      {old.length > 1 && <OldPlants plants={old} view={view} />}
    </section>
  );
}
