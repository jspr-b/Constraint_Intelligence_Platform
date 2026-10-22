"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect } from "react";
import { EmptyState } from "./EmptyState";
import { TechnicalDetails } from "./Problems";

/** A page crashed: say so plainly, offer to try again, keep the details for IT. */
export function PageCrash({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  const t = useTranslations("problems");
  useEffect(() => console.error(error), [error]);
  const lines = [
    error.message,
    ...(error.digest ? [t("reference", { digest: error.digest })] : []),
  ];
  return (
    <div role="alert">
      <EmptyState title={t("pageTitle")}>
        <p className="m-0">{t("pageBody")}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={retry}
            className="cursor-pointer rounded-control border border-line-strong bg-transparent px-2 py-1 text-sm text-accent"
          >
            {t("tryAgain")}
          </button>
          <Link href="/">{t("home")}</Link>
        </div>
        <div className="mt-3">
          <TechnicalDetails lines={lines} />
        </div>
      </EmptyState>
    </div>
  );
}
