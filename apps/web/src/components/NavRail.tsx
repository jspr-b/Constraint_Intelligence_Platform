"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Compass } from "lucide-react";
import { MicroLabel } from "@cip/ui";
import { GROUPS, type PageKey } from "@/lib/pages";

/** Grouped menu (Diagnose, Plan, Operate, Prove, Setup) with only the pages the role may open. */
export function NavRail({
  pages,
  active,
  onGuide,
}: {
  pages: Set<PageKey>;
  active: PageKey | null;
  /** Reopen the getting-started guide; absent while it is shown. */
  onGuide?: (() => void) | undefined;
}) {
  const t = useTranslations("nav");
  const tg = useTranslations("guide");
  return (
    <nav
      aria-label={t("label")}
      className="flex w-56 shrink-0 flex-col gap-px overflow-y-auto border-r border-line px-2 py-3"
    >
      {GROUPS.map((group) => {
        const visible = group.pages.filter((p) => pages.has(p.key));
        if (visible.length === 0) return null;
        return (
          <div key={group.key} className="flex flex-col gap-px pb-3">
            <h2 className="m-0 px-3 pt-1 pb-1">
              <MicroLabel>{t(`groups.${group.key}`)}</MicroLabel>
            </h2>
            {visible.map(({ key, icon: Icon }) => {
              const current = key === active;
              return (
                <Link
                  key={key}
                  href={`/${key}`}
                  aria-current={current ? "page" : undefined}
                  className={
                    "flex min-h-8 items-center gap-2.5 rounded-control px-3 text-sm no-underline outline-none " +
                    "focus-visible:outline-1 focus-visible:outline-accent " +
                    (current
                      ? "bg-raised text-accent shadow-[inset_2px_0_0_var(--accent)]"
                      : "text-muted hover:bg-raised hover:text-text")
                  }
                >
                  <Icon aria-hidden="true" size={16} strokeWidth={1.5} />
                  {t(`pages.${key}`)}
                </Link>
              );
            })}
          </div>
        );
      })}
      {onGuide && (
        <button
          type="button"
          onClick={onGuide}
          className="mt-auto flex min-h-8 cursor-pointer items-center gap-2.5 rounded-control border-0 bg-transparent px-3 text-left text-sm text-muted hover:bg-raised hover:text-text"
        >
          <Compass aria-hidden="true" size={16} strokeWidth={1.5} />
          {tg("reopen")}
        </button>
      )}
    </nav>
  );
}
