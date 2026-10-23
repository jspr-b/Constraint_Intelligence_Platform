"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ComponentType } from "react";
import type { PageKey } from "@/lib/pages";
import { AccessPage } from "./pages/AccessPage";
import { CalendarPage } from "./pages/CalendarPage";
import { ConnectionsPage } from "./pages/ConnectionsPage";
import { DataQualityPage } from "./pages/DataQualityPage";
import { ImportPage } from "./pages/ImportPage";
import { LossPage } from "./pages/LossPage";
import { MachinesPage } from "./pages/MachinesPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ReportPage } from "./pages/ReportPage";
import { RunPage } from "./pages/RunPage";
import { SetupPage } from "./pages/SetupPage";
import { UsersPage } from "./pages/UsersPage";
import { EmptyState } from "./EmptyState";
import { useOnboarding } from "./GettingStarted";
import { PageHeader } from "./PageHeader";
import { useView } from "./ViewContext";
import { termTags } from "./terms";

/** Pages that are built; every other page shows an honest 'not built yet'. */
const BUILT: Partial<Record<PageKey, ComponentType>> = {
  access: AccessPage,
  calendar: CalendarPage,
  conn: ConnectionsPage,
  data: DataQualityPage,
  import: ImportPage,
  loss: LossPage,
  machines: MachinesPage,
  main: OverviewPage,
  report: ReportPage,
  run: RunPage,
  setup: SetupPage,
  users: UsersPage,
};

const NEXT_PAGE: Record<string, string> = {
  plant: "/setup",
  upload: "/import",
  check: "/data",
  answer: "/main",
};

export function PageView({ page }: { page: PageKey }) {
  const t = useTranslations();
  const view = useView();
  const onboarding = useOnboarding();
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
        <p className="m-0 text-text">{t.rich(`empty.pages.${page}`, termTags)}</p>
        <p className="m-0 mt-1">{t("empty.noNumbers")}</p>
        <p className="m-0 mt-3">
          {t("empty.today")}{" "}
          {onboarding.data && !onboarding.data.complete ? (
            <Link href={NEXT_PAGE[onboarding.data.next_step ?? "plant"] ?? "/setup"}>
              {t("empty.todayLinks.setup")}
            </Link>
          ) : (
            <Link href="/data">{t("empty.todayLinks.data")}</Link>
          )}
        </p>
      </EmptyState>
    </div>
  );
}
