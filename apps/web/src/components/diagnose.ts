"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { isMissing } from "@cip/ui";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

/** Shared reads for the Diagnose pages: facts, periods, machine names. The API calculates. */
export type Fact = components["schemas"]["FactOut"];
export type Period = components["schemas"]["PeriodOut"];
export type Family = Fact["family"];

export function useFacts(
  plant: string | null,
  query: {
    family?: Family[];
    resource_code?: string;
    period_kind?: "all" | "month" | "week" | "day";
    period_start_at?: string;
  },
  enabled = true,
) {
  return useQuery({
    queryKey: ["facts", plant, query],
    enabled: plant !== null && enabled,
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/facts", {
          params: { path: { plant_code: plant ?? "" }, query },
        })
      ).data ?? null,
    refetchInterval: (q) => (q.state.data?.run?.status === "calculating" ? 3000 : false),
  });
}

export function useFactPeriods(plant: string | null) {
  return useQuery({
    queryKey: ["fact-periods", plant],
    enabled: plant !== null,
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/facts/periods", {
          params: { path: { plant_code: plant ?? "" } },
        })
      ).data ?? [],
  });
}

/** "Paint line (PNT-01)" for a step code, or "Finishing team (FINISH-TEAM)" for a shared team,
 * from the plant's steps and teams. */
export function useMachineLabel(plant: string | null): (code: string) => string {
  const resources = useQuery({
    queryKey: ["resources", plant],
    enabled: plant !== null,
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/resources", {
          params: { path: { plant_code: plant ?? "" } },
        })
      ).data ?? [],
  });
  const teams = useTeams(plant);
  const names = new Map([
    ...(resources.data ?? []).map((r) => [r.resource_code, r.name] as const),
    ...teams.map((t) => [t.team_code, t.name] as const),
  ]);
  return (code: string) => `${names.get(code) ?? code} (${code})`;
}

/** Teams shared by several steps (ADR-0009): code, name and the steps they cover. */
export function useTeams(plant: string | null) {
  const teams = useQuery({
    queryKey: ["teams", plant],
    enabled: plant !== null,
    queryFn: async () =>
      (
        await api.GET("/plants/{plant_code}/teams", {
          params: { path: { plant_code: plant ?? "" } },
        })
      ).data ?? [],
  });
  return teams.data ?? [];
}

/** A period's name: "Whole data period", "August 2026" or "Week of Aug 3, 2026". */
export function usePeriodName(): (
  p: { period_kind: string; period_start_at: string } | undefined,
) => string {
  const t = useTranslations("machines");
  const locale = useLocale();
  return (p) => {
    if (!p || p.period_kind === "all") return t("periodAll");
    const start = new Date(p.period_start_at);
    if (p.period_kind === "month") {
      return new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(start);
    }
    return t("periodWeek", {
      date: new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(start),
    });
  };
}

export function valueOf(fact: Fact | undefined): number | null {
  if (!fact || isMissing(fact.figure.value)) return null;
  return fact.figure.value;
}
