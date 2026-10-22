"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, type ReactNode } from "react";
import { LiveDot } from "@cip/ui";
import { isPageKey, type PageKey } from "@/lib/pages";
import type { Theme } from "@/lib/prefs";
import { effectiveView, useAccessMatrix, useApiHealth, useMe, type View } from "@/lib/session";
import { Drawer } from "./Drawer";
import { EmptyState } from "./EmptyState";
import { RoleSwitch, SignOut, ThemeToggle } from "./HeaderControls";
import { NavRail } from "./NavRail";
import { ViewContext } from "./ViewContext";

function ApiStatus() {
  const t = useTranslations("header");
  const health = useApiHealth();
  const label = { checking: t("apiChecking"), ok: t("apiOk"), down: t("apiDown") }[health];
  return (
    <span role="status" className="inline-flex items-center gap-1.5 font-mono text-xs text-muted">
      {health === "ok" ? (
        <LiveDot />
      ) : (
        <span aria-hidden="true">{health === "down" ? "✕" : "…"}</span>
      )}
      {label}
    </span>
  );
}

export function Shell({
  children,
  theme,
  viewAs,
}: {
  children: ReactNode;
  theme: Theme;
  viewAs: string | undefined;
}) {
  const t = useTranslations();
  const session = useMe();
  const canReadMatrix = session.status === "ready" && session.me.pages.includes("access");
  const matrix = useAccessMatrix(canReadMatrix);
  const segment = usePathname().split("/")[1] ?? "";
  const active: PageKey | null = isPageKey(segment) ? segment : null;
  const view: View | null =
    session.status === "ready" ? effectiveView(session.me, matrix, viewAs) : null;
  const station = view?.role === "station";
  const router = useRouter();
  useEffect(() => {
    if (session.status === "signed-out") router.replace("/login");
  }, [session.status, router]);

  let body: ReactNode = children;
  if (session.status === "loading") body = <p className="text-muted">{t("shell.loading")}</p>;
  else if (session.status === "unreachable")
    body = <EmptyState title={t("header.apiDown")}>{t("shell.apiUnreachable")}</EmptyState>;
  else if (session.status === "signed-out")
    body = (
      <EmptyState title={t("login.title")}>
        {t("shell.signInRequired")} <Link href="/login">{t("login.title")}</Link>
      </EmptyState>
    );

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:bg-surface focus:p-2"
      >
        {t("app.skipToContent")}
      </a>
      <header className="flex min-h-12 flex-wrap items-center justify-between gap-4 border-b border-line px-5">
        <div className="flex flex-wrap items-center gap-4">
          <span className="font-mono text-xs font-medium tracking-[0.12em] uppercase">
            {t("app.name")}
          </span>
          <ApiStatus />
        </div>
        <div className="flex flex-wrap items-center gap-4">
          {view && matrix && <RoleSwitch role={view.role} matrix={matrix} />}
          <ThemeToggle initial={theme} />
          {view && <SignOut />}
        </div>
      </header>
      <div className="flex min-h-0 flex-1">
        {view && !station && <NavRail pages={view.pages} active={active} />}
        <main id="content" tabIndex={-1} className="min-w-0 flex-1 p-5 outline-none">
          {view ? <ViewContext value={view}>{body}</ViewContext> : body}
        </main>
        {view && !station && <Drawer />}
      </div>
    </div>
  );
}
