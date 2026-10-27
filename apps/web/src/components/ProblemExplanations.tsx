"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { Button, MicroLabel } from "@cip/ui";
import type { components } from "@/lib/api/schema";
import { Count } from "./Figure";

type Explanations = components["schemas"]["AiExplanationsOut"];

/** Why rows were rejected and how to fix the export, per reason: the standard explanation
 *  always, the AI's for this export when IT asked for it (ADR-0011 §4). */
export function ProblemExplanations({
  codes,
  example,
  explanations,
  ask,
}: {
  /** Rejected rows per reason code. */
  codes: Record<string, number>;
  /** How the export writes a date and time, for the date reason. */
  example?: string | null | undefined;
  explanations: Explanations | null | undefined;
  /** On the Import page: the AI's state and the ask button for roles that fix rows.
   *  Without it (Data quality) the page links to the Import page. */
  ask?: {
    ai: Explanations["state"];
    canAsk: boolean;
    pending: boolean;
    error: string | null;
    onAsk: () => void;
  };
}) {
  const t = useTranslations("import.explain");
  const tr = useTranslations("import.rejected");
  const tf = useTranslations("figure");
  const entries = Object.entries(codes).filter(([, n]) => n > 0);
  if (entries.length === 0) return null;
  const byAi = new Map((explanations?.items ?? []).map((e) => [e.code, e]));
  const failed = explanations && explanations.state !== "connected" ? explanations.state : null;
  return (
    <section aria-label={t("label")} className="mb-4 flex flex-col gap-3">
      <h3 className="m-0 text-[11px] font-medium uppercase tracking-[0.08em] text-muted">
        {t("label")}
      </h3>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {entries.map(([code, n]) => {
          const ai = byAi.get(code);
          const name = tr.has(`codeShort.${code}`) ? tr(`codeShort.${code}`) : code;
          return (
            <li key={code} className="flex flex-col gap-1 border-l-2 border-line pl-3 text-sm">
              <p className="m-0">
                <span className="font-medium">{name}</span> ·{" "}
                <Count
                  value={n}
                  label={t("rowsOf", { reason: name })}
                  source={{ what: tf("src.rejectedRows") }}
                />{" "}
                {t("rows", { count: n })}
              </p>
              <p className="m-0">
                {code === "not_a_datetime" && !example
                  ? t("dateUnreadable")
                  : tr.has(`code.${code}`)
                    ? tr(`code.${code}`, { example: example ?? "" })
                    : null}{" "}
                {t.has(`fix.${code}`) ? t(`fix.${code}`) : t("fix.other")}
              </p>
              {ai && (
                <div className="mt-1 flex flex-col gap-1 border-l-2 border-accent pl-3">
                  <MicroLabel>{t("byAi")}</MicroLabel>
                  <p className="m-0">{ai.explanation}</p>
                  <p className="m-0">
                    <span className="font-medium">{t("aiFix")}</span> {ai.fix}
                  </p>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {failed && <p className="m-0 text-xs text-muted">{t(`failed.${failed}`)}</p>}
      {ask ? (
        ask.ai === "not_connected" ? (
          <p className="m-0 text-xs text-muted">{t("notConnected")}</p>
        ) : ask.canAsk ? (
          <div className="flex flex-col gap-1">
            <div>
              <Button variant="secondary" isDisabled={ask.pending} onPress={ask.onAsk}>
                {ask.pending ? t("asking") : explanations ? t("askAgain") : t("ask")}
              </Button>
            </div>
            <p className="m-0 text-xs text-muted">{t("sent")}</p>
            {ask.error && (
              <p role="alert" className="m-0 text-sm text-bad">
                {ask.error}
              </p>
            )}
          </div>
        ) : (
          !explanations && <p className="m-0 text-xs text-muted">{t("askWho")}</p>
        )
      ) : (
        !explanations && (
          <p className="m-0 text-xs text-muted">
            {t("onImport")} <Link href="/import">{t("toImport")}</Link>
          </p>
        )
      )}
    </section>
  );
}
