"use client";

import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { useTranslations } from "next-intl";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { MicroLabel } from "@cip/ui";
import { useDetails } from "./Details";
import { Glossary } from "./Term";

/** Right Details drawer: what a page put there (e.g. how a number is made), else the glossary. */
export function Drawer() {
  const t = useTranslations("drawer");
  const details = useDetails();
  const { open, setOpen } = details;
  const body = useRef<HTMLDivElement>(null);
  const pathname = usePathname();
  const { clear, content } = details;
  // A new page starts on the glossary again.
  useEffect(() => clear(), [pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  // Showing details opens the drawer and moves focus there, so keyboard and screen readers follow.
  useEffect(() => {
    if (content) requestAnimationFrame(() => body.current?.focus());
  }, [content]);
  const Icon = open ? PanelRightClose : PanelRightOpen;
  return (
    <aside
      aria-label={t("label")}
      className={`flex shrink-0 flex-col border-l border-line ${open ? "w-72" : "w-12"}`}
    >
      <div className="flex min-h-10 items-center justify-between border-b border-line px-3">
        {open && <MicroLabel>{t("label")}</MicroLabel>}
        <button
          type="button"
          aria-expanded={open}
          aria-label={open ? t("close") : t("open")}
          onClick={() => setOpen(!open)}
          className="inline-flex min-h-7 min-w-7 cursor-pointer items-center justify-center rounded-control border-0 bg-transparent text-muted hover:bg-raised hover:text-text focus-visible:outline-1 focus-visible:outline-accent"
        >
          <Icon aria-hidden="true" size={16} strokeWidth={1.5} />
        </button>
      </div>
      {open && (
        <div ref={body} tabIndex={-1} className="overflow-y-auto outline-none">
          {content ?? <Glossary />}
        </div>
      )}
    </aside>
  );
}
