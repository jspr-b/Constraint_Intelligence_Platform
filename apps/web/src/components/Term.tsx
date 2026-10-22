"use client";

import { useTranslations } from "next-intl";
import { useId, useState, type ReactNode } from "react";

import { TERMS, type TermKey } from "@/lib/glossary";

/**
 * A word a client may not know, with its one-line explanation from the glossary.
 * Shows on hover, on keyboard focus and on tap; Escape closes it.
 */
export function Term({ id, children }: { id: TermKey; children: ReactNode }) {
  const t = useTranslations("glossary.terms");
  const tip = useId();
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <button
        type="button"
        aria-describedby={open ? tip : undefined}
        aria-expanded={open}
        onClick={() => setOpen(true)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        className="cursor-help border-0 border-b border-dotted border-current bg-transparent p-0 font-[inherit] text-[length:inherit] text-inherit"
      >
        {children}
      </button>
      {open && (
        <span
          id={tip}
          role="tooltip"
          className="absolute top-full left-0 z-30 mt-1 w-64 rounded-control border border-line-strong bg-surface p-2 text-xs font-normal text-text normal-case shadow-sm"
        >
          <strong className="font-medium">{t(`${id}.name`)}</strong> · {t(`${id}.text`)}
        </span>
      )}
    </span>
  );
}

/** The whole glossary, for the details drawer. */
export function Glossary() {
  const t = useTranslations("glossary");
  return (
    <section aria-label={t("title")} className="flex flex-col gap-2 p-3 text-sm">
      <h2 className="m-0 font-mono text-xs font-medium tracking-[0.08em] text-muted uppercase">
        {t("title")}
      </h2>
      <dl className="m-0 flex flex-col gap-2">
        {TERMS.map((id) => (
          <div key={id}>
            <dt className="font-medium">{t(`terms.${id}.name`)}</dt>
            <dd className="m-0 text-muted">{t(`terms.${id}.text`)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
