"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ComponentType } from "react";
import { PAGES, type PageKey } from "@/lib/pages";
import { AccessPage } from "./pages/AccessPage";
import { CalendarPage } from "./pages/CalendarPage";
import { ConnectionsPage } from "./pages/ConnectionsPage";
import { ImportPage } from "./pages/ImportPage";
import { SetupPage } from "./pages/SetupPage";
import { UsersPage } from "./pages/UsersPage";
import { EmptyState } from "./EmptyState";
import { PageHeader } from "./PageHeader";
import { useView } from "./ViewContext";

/** Pages that are built; every other page shows an honest 'not built yet'. */
const BUILT: Partial<Record<PageKey, ComponentType>> = {
  access: AccessPage,
  calendar: CalendarPage,
  conn: ConnectionsPage,
  import: ImportPage,
  setup: SetupPage,
  users: UsersPage,
};

export function PageView({ page }: { page: PageKey }) {
  const t = useTranslations();
  const view = useView();
  if (!view) return null;
  const title = t(`nav.pages.${page}`);
  if (view.role === "station" && page !== "station") {
    return (
      <EmptyState title={title}>
        {t("shell.stationOnly")} <Link href="/station">{t("nav.pages.station")}</Link>
      </EmptyState>
    );
  }
  if (!view.pages.has(page)) {
    return <EmptyState title={title}>{t("shell.notAllowed")}</EmptyState>;
  }
  const Built = BUILT[page];
  if (Built) return <Built />;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        page={page}
        actions={
          page === "shift" ? (
            <Link href="/shift/tv" className="text-sm text-accent">
              {t("tv.open")}
            </Link>
          ) : undefined
        }
      />
      <EmptyState title={t("empty.notBuilt")}>
        <p className="m-0">{t(`empty.builtBy.${PAGES[page].builtBy}`)}</p>
        <p className="m-0 mt-1">{t("empty.noNumbers")}</p>
      </EmptyState>
    </div>
  );
}
