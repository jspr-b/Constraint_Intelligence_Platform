"use client";

import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { MicroLabel } from "@cip/ui";

/** Right detail drawer. Pages put item details here; until then it shows an empty state. */
export function Drawer() {
  const t = useTranslations("drawer");
  const [open, setOpen] = useState(true);
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
      {open && <p className="m-0 p-3 text-sm text-muted">{t("empty")}</p>}
    </aside>
  );
}
