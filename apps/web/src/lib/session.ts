"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import type { components } from "./api/schema";
import { isPageKey, type PageKey, type Role } from "./pages";

export type Me = components["schemas"]["MeOut"];
export type AccessMatrix = components["schemas"]["AccessOut"];

export type SessionState =
  | { status: "loading" }
  | { status: "signed-out" }
  | { status: "unreachable" }
  | { status: "ready"; me: Me };

export function useMe(): SessionState {
  const query = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const { data, response } = await api.GET("/auth/me");
      return { data, status: response.status };
    },
    retry: false,
  });
  if (query.isPending) return { status: "loading" };
  if (query.isError || !query.data) return { status: "unreachable" };
  if (query.data.status === 401) return { status: "signed-out" };
  if (!query.data.data) return { status: "unreachable" };
  return { status: "ready", me: query.data.data };
}

/** The COO's access matrix; readable by every role that may open the Access page. */
export function useAccessMatrix(enabled: boolean): AccessMatrix | undefined {
  const query = useQuery({
    queryKey: ["access"],
    queryFn: async () => (await api.GET("/access")).data ?? null,
    enabled,
    retry: false,
  });
  return query.data ?? undefined;
}

export function useApiHealth(): "checking" | "ok" | "down" {
  const query = useQuery({
    queryKey: ["health"],
    queryFn: async () => (await api.GET("/health")).response.ok,
    refetchInterval: 30_000,
    retry: false,
  });
  if (query.isPending) return "checking";
  return query.data ? "ok" : "down";
}

export interface View {
  role: Role;
  pages: Set<PageKey>;
  startPage: PageKey;
  preview: boolean;
}

/**
 * What the shell shows: the signed-in role, or the role chosen in the role switch (a preview
 * from the access matrix). The API still enforces the session's own role on every call.
 */
export function effectiveView(
  me: Me,
  matrix: AccessMatrix | undefined,
  viewAs: string | undefined,
): View {
  const chosen = matrix?.roles.find((r) => r.role === viewAs);
  const source = chosen ?? { role: me.role, pages: me.pages, start_page: me.start_page };
  return {
    role: source.role as Role,
    pages: new Set(source.pages.filter(isPageKey)),
    startPage: isPageKey(source.start_page) ? source.start_page : "main",
    preview: chosen !== undefined && chosen.role !== me.role,
  };
}
