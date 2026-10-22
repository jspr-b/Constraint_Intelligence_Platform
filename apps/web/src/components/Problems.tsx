"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useState, useSyncExternalStore, type ReactNode } from "react";
import { ApiError } from "@/lib/api/client";
import { NEXT_STEP } from "@/lib/api/nextStep";
import { useApiHealth } from "@/lib/session";

const BUTTON =
  "cursor-pointer rounded-control border border-line-strong bg-transparent px-2 py-1 text-sm text-accent";

/** What failed, for the person who has to fix it. Folded away by default. */
export function TechnicalDetails({ lines }: { lines: string[] }) {
  const t = useTranslations("problems");
  return (
    <details className="text-xs text-muted">
      <summary className="cursor-pointer">{t("details")}</summary>
      <ul className="m-0 mt-1 list-none p-0 font-mono">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </details>
  );
}

function Banner({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div
      role="alert"
      className="mb-4 flex flex-col gap-2 rounded-panel border border-bad px-4 py-3 text-sm"
    >
      <strong className="font-medium">{title}</strong>
      {children}
    </div>
  );
}

interface Failure {
  message: string;
  code: string | null;
  technical: string;
}

function failureOf(error: unknown, fallback: string): Failure {
  if (error instanceof ApiError) {
    return { message: error.message, code: error.problem.code, technical: error.technical };
  }
  const text = error instanceof Error ? error.message : String(error);
  return { message: "", code: null, technical: `${fallback}: ${text}` };
}

/** Reads on this page that failed (active queries in error), as a stable JSON snapshot. */
function useFailedReads(): { failures: Failure[]; retry: () => void } {
  const queries = useQueryClient();
  const cache = queries.getQueryCache();
  const snapshot = useCallback(
    () =>
      JSON.stringify(
        cache
          .getAll()
          .filter((q) => q.state.status === "error" && q.isActive() && q.queryKey[0] !== "health")
          .map((q) => failureOf(q.state.error, JSON.stringify(q.queryKey))),
      ),
    [cache],
  );
  const text = useSyncExternalStore(
    (notify) => cache.subscribe(notify),
    snapshot,
    () => "[]",
  );
  const retry = () =>
    void queries.refetchQueries({ predicate: (q) => q.state.status === "error", type: "active" });
  return { failures: JSON.parse(text) as Failure[], retry };
}

/** The latest write the server refused (ApiError from ensureOk), until it is closed. */
function useFailedWrite(): { failure: Failure | null; dismiss: () => void } {
  const cache = useQueryClient().getMutationCache();
  const [dismissed, setDismissed] = useState<number[]>([]);
  const snapshot = useCallback(() => {
    const failed = cache
      .getAll()
      .filter((m) => m.state.status === "error" && m.state.error instanceof ApiError)
      .at(-1);
    return failed
      ? JSON.stringify({ id: failed.mutationId, ...failureOf(failed.state.error, "write") })
      : "";
  }, [cache]);
  const text = useSyncExternalStore(
    (notify) => cache.subscribe(notify),
    snapshot,
    () => "",
  );
  const parsed = text ? (JSON.parse(text) as Failure & { id: number }) : null;
  return {
    failure: parsed && !dismissed.includes(parsed.id) ? parsed : null,
    dismiss: () => parsed && setDismissed((d) => [...d, parsed.id]),
  };
}

/** The server's own words, plus the next step when the code has one. */
function Reason({ failure }: { failure: Failure }) {
  const t = useTranslations("problems");
  const href = failure.code ? NEXT_STEP[failure.code] : undefined;
  if (!failure.message) return null;
  return (
    <p className="m-0">
      {failure.message}{" "}
      {href && failure.code && <Link href={href}>{t(`next.${failure.code}`)}</Link>}
    </p>
  );
}

/**
 * One plain message when something could not load, instead of pages failing one by one:
 * the API is unreachable, or some reads on this page failed.
 */
export function Problems() {
  const t = useTranslations("problems");
  const health = useApiHealth();
  const queries = useQueryClient();
  const failed = useFailedReads();
  const write = useFailedWrite();
  if (health === "down") {
    return (
      <Banner title={t("apiDownTitle")}>
        <p className="m-0">{t("apiDownBody")}</p>
        <div>
          <button
            type="button"
            className={BUTTON}
            onClick={() => void queries.refetchQueries({ type: "active" })}
          >
            {t("tryNow")}
          </button>
        </div>
      </Banner>
    );
  }
  if (write.failure) {
    return (
      <Banner title={t("writeTitle")}>
        <Reason failure={write.failure} />
        <p className="m-0 text-muted">{t("writeBody")}</p>
        <div>
          <button type="button" className={BUTTON} onClick={write.dismiss}>
            {t("dismiss")}
          </button>
        </div>
        <TechnicalDetails lines={[write.failure.technical]} />
      </Banner>
    );
  }
  if (failed.failures.length === 0) return null;
  // One line per distinct reason, keeping the first failure that gave it.
  const reasons = failed.failures.filter(
    (f, i, all) => f.message && all.findIndex((g) => g.message === f.message) === i,
  );
  return (
    <Banner title={t("partTitle")}>
      {reasons.map((f) => (
        <Reason key={f.message} failure={f} />
      ))}
      <p className="m-0 text-muted">{t("partBody")}</p>
      <div>
        <button type="button" className={BUTTON} onClick={failed.retry}>
          {t("tryAgain")}
        </button>
      </div>
      <TechnicalDetails lines={[...new Set(failed.failures.map((f) => f.technical))]} />
    </Banner>
  );
}
