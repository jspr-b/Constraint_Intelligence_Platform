"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect } from "react";
import { MicroLabel } from "@cip/ui";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import type { View } from "@/lib/session";

type Step = components["schemas"]["StepOut"];

/** Where each step is done in the app. */
const STEP_PAGE: Record<Step["key"], string> = {
  plant: "/setup",
  upload: "/import",
  check: "/data",
  answer: "/main",
};

const GLYPH: Record<"done" | "next" | "todo" | "later", string> = {
  done: "✓",
  next: "→",
  todo: "○",
  later: "…",
};

/** Query keys whose data moves the client along: a new plant, an import that ran. */
const MOVES_ONBOARDING = new Set(["plants", "imports"]);

export function useOnboarding() {
  const queries = useQueryClient();
  useEffect(
    () =>
      queries.getQueryCache().subscribe((event) => {
        const key = event.query.queryKey[0];
        if (
          event.type === "updated" &&
          event.action.type === "success" &&
          MOVES_ONBOARDING.has(String(key))
        ) {
          void queries.invalidateQueries({ queryKey: ["onboarding"] });
        }
      }),
    [queries],
  );
  return useQuery({
    queryKey: ["onboarding"],
    queryFn: async () => (await api.GET("/onboarding")).data ?? null,
    // Faster while an import or its calculation is under way, so the guide moves on by itself.
    refetchInterval: (q) =>
      q.state.data?.steps.some((s) => s.detail === "running" || s.detail === "calculating")
        ? 3_000
        : 15_000,
  });
}

/**
 * Getting started: add your plant → upload your exports → check your data → see your bottleneck.
 * Every state comes from the API (real data), and roles that cannot set up learn who can.
 */
export function GettingStarted({ view, onHide }: { view: View; onHide: () => void }) {
  const t = useTranslations("guide");
  const query = useOnboarding();
  const o = query.data;
  if (!o) return null;
  const canSetUp = view.decisions.has("import_run_diagnostic");
  const available = o.steps.filter((s) => s.state !== "later");
  const done = available.filter((s) => s.state === "done").length;
  const contacts = o.setup_contacts.join(", ");

  const line = (s: Step): string => {
    if (s.key === "check" && s.detail === "confirm") {
      return t("check.confirm", { items: s.missing.map((m) => t(`items.${m}`)).join(", ") });
    }
    if (s.key === "check" && s.detail === "optional") {
      return t("check.optional", { items: s.missing.map((m) => t(`items.${m}`)).join(", ") });
    }
    if (s.state === "done") {
      return s.key === "plant"
        ? t("plant.done", { plant: o.plant_name ?? "" })
        : t(`${s.key}.done`);
    }
    if (s.state === "later") return t(`${s.key}.later`);
    if (s.key === "check" && s.detail === "missing") {
      return t("check.missing", { items: s.missing.map((m) => t(`items.${m}`)).join(", ") });
    }
    if (s.key === "upload" && s.detail) return t(`upload.${s.detail}`);
    if (!canSetUp && s.key !== "check") {
      return contacts ? t("waitingFor", { who: contacts }) : t("waitingForIt");
    }
    return t(`${s.key}.todo`);
  };

  const goLabel = (s: Step): string => {
    if (s.key === "upload" && s.detail === "uploaded") return "upload.goRun";
    if (s.key === "upload" && s.detail === "failed") return "upload.goFailed";
    if (s.key === "upload" && s.detail === "numbers_failed") return "upload.goFailed";
    return `${s.key}.go`;
  };

  return (
    <section
      aria-label={t("title")}
      className="mb-5 flex flex-col gap-3 rounded-panel border border-line bg-surface p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <h2 className="m-0 text-base font-medium">{t("title")}</h2>
          <MicroLabel>
            {o.complete ? t("allDone") : t("progress", { done, total: available.length })}
          </MicroLabel>
        </div>
        <button
          type="button"
          onClick={onHide}
          className="cursor-pointer rounded-control border border-line-strong bg-transparent px-2 py-1 text-xs text-muted"
        >
          {t("hide")}
        </button>
      </div>
      <ol className="m-0 flex list-none flex-col gap-2 p-0">
        {o.steps.map((s, i) => {
          const next = s.key === o.next_step;
          const state = next ? "next" : s.state === "done" ? "done" : s.state;
          return (
            <li key={s.key} className="flex items-start gap-3 text-sm">
              <span
                aria-hidden="true"
                className={`w-4 font-mono ${state === "done" ? "text-ok" : next ? "text-accent" : "text-muted"}`}
              >
                {GLYPH[state]}
              </span>
              <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className={next ? "font-medium" : s.state === "done" ? "text-muted" : ""}>
                  {i + 1}. {t(`${s.key}.title`)}
                  <span className="sr-only"> ({t(`state.${state}`)})</span>
                </span>
                <span className="text-muted">{line(s)}</span>
                {next && (canSetUp || s.key === "check") && (
                  <Link href={STEP_PAGE[s.key]} className="text-accent">
                    {t(goLabel(s))}
                  </Link>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
