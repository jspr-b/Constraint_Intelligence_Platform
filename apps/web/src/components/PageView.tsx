"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { MicroLabel } from "@cip/ui";
import { PAGES, groupOf, type PageKey } from "@/lib/pages";
import { EmptyState } from "./EmptyState";
import { useView } from "./ViewContext";

/** A page that is not built yet: title and an honest empty state. */
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
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <MicroLabel>{t(`nav.groups.${groupOf(page)}`)}</MicroLabel>
          <h1 className="m-0 text-xl font-medium">{title}</h1>
        </div>
        {page === "shift" && (
          <Link href="/shift/tv" className="text-sm text-accent">
            {t("tv.open")}
          </Link>
        )}
      </div>
      <EmptyState title={t("empty.notBuilt")}>
        <p className="m-0">{t(`empty.builtBy.${PAGES[page].builtBy}`)}</p>
        <p className="m-0 mt-1">{t("empty.noNumbers")}</p>
      </EmptyState>
    </div>
  );
}
