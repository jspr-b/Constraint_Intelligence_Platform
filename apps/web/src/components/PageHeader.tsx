"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { MicroLabel } from "@cip/ui";
import { groupOf, type PageKey } from "@/lib/pages";

/** Group micro label, page title, optional headline and actions on the right. */
export function PageHeader({
  page,
  headline,
  actions,
}: {
  page: PageKey;
  headline?: ReactNode;
  actions?: ReactNode;
}) {
  const t = useTranslations("nav");
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="flex flex-col gap-1">
        <MicroLabel>{t(`groups.${groupOf(page)}`)}</MicroLabel>
        <h1 className="m-0 text-xl font-medium">{t(`pages.${page}`)}</h1>
        {headline && <p className="m-0 text-sm text-muted">{headline}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
