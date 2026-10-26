"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { isMissing, MicroLabel } from "@cip/ui";
import { api } from "@/lib/api/client";
import { useDetection } from "../ConstraintBanner";
import { useFacts, useMachineLabel } from "../diagnose";
import { EmptyState } from "../EmptyState";
import { PageHeader } from "../PageHeader";
import { PlantPicker, usePlant } from "../PlantPicker";

type State = "done" | "running" | "todo" | "failed" | "waiting";

const GLYPH: Record<State, { glyph: string; colour: string }> = {
  done: { glyph: "✓", colour: "text-ok" },
  running: { glyph: "◌", colour: "text-accent" },
  todo: { glyph: "→", colour: "text-accent" },
  failed: { glyph: "✕", colour: "text-bad" },
  waiting: { glyph: "○", colour: "text-faint" },
};

interface Step {
  key: "data" | "numbers" | "bottleneck" | "cost";
  state: State;
  detail: string;
  href: string;
  go: string;
}

/** Diagnostic run: data in → numbers calculated → bottleneck found → cost calculated. */
export function RunPage() {
  const t = useTranslations("run");
  const tg = useTranslations("guide");
  const picker = usePlant();
  const { plant } = picker;
  const label = useMachineLabel(plant);
  const onboarding = useQuery({
    queryKey: ["onboarding", plant],
    enabled: plant !== null,
    queryFn: async () =>
      (await api.GET("/onboarding", { params: { query: { plant_code: plant } } })).data ?? null,
    refetchInterval: (q) =>
      q.state.data?.steps.some((s) => s.detail === "running" || s.detail === "calculating")
        ? 3000
        : 15_000,
  });
  const detection = useDetection(plant, { period_kind: "all" });
  const found = detection.data?.detections[0];
  const internal = found?.kind === "internal" && !!found.resource_code;
  const loss = useFacts(plant, { family: ["loss"] }, internal);

  const header = <PageHeader page="run" actions={<PlantPicker {...picker} />} />;
  if (picker.plants && picker.plants.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        {header}
        <EmptyState title={t("noPlant")}>
          <Link href="/setup">{t("toSetup")}</Link>
        </EmptyState>
      </div>
    );
  }
  const o = onboarding.data;
  if (!o) return header;
  const upload = o.steps.find((s) => s.key === "upload");
  const check = o.steps.find((s) => s.key === "check");
  const run = detection.data?.run;

  // 1. Data in: the latest import, and whether it covers what a diagnosis needs.
  let data: Step;
  if (!upload || (upload.state === "todo" && !upload.detail)) {
    data = {
      key: "data",
      state: "todo",
      detail: t("data.none"),
      href: "/import",
      go: t("data.goUpload"),
    };
  } else if (upload.detail === "uploaded") {
    data = {
      key: "data",
      state: "todo",
      detail: t("data.uploaded"),
      href: "/import",
      go: t("data.goRun"),
    };
  } else if (upload.detail === "running") {
    data = {
      key: "data",
      state: "running",
      detail: t("data.running"),
      href: "/import",
      go: t("data.goImport"),
    };
  } else if (upload.detail === "failed") {
    data = {
      key: "data",
      state: "failed",
      detail: t("data.failed"),
      href: "/import",
      go: t("data.goImport"),
    };
  } else if (check?.detail === "missing") {
    data = {
      key: "data",
      state: "todo",
      detail: t("data.missing", { items: check.missing.map((m) => tg(`items.${m}`)).join(", ") }),
      href: "/data",
      go: t("data.goQuality"),
    };
  } else {
    data = {
      key: "data",
      state: "done",
      detail: t("data.done"),
      href: "/data",
      go: t("data.goQuality"),
    };
  }

  // 2. Numbers calculated from the latest import.
  let numbers: Step;
  if (data.state !== "done") {
    numbers = {
      key: "numbers",
      state: "waiting",
      detail: t("numbers.waiting"),
      href: "/import",
      go: t("data.goImport"),
    };
  } else if (!run || (run.status === "calculating" && !run.finished_at)) {
    numbers = {
      key: "numbers",
      state: "running",
      detail: t("numbers.running"),
      href: "/import",
      go: t("data.goImport"),
    };
  } else if (run.status === "failed" && !run.finished_at) {
    numbers = {
      key: "numbers",
      state: "failed",
      detail: t("numbers.failed"),
      href: "/import",
      go: t("data.goImport"),
    };
  } else {
    numbers = {
      key: "numbers",
      state: "done",
      detail: t("numbers.done"),
      href: "/machines",
      go: t("numbers.go"),
    };
  }

  // 3. Bottleneck found (or: no machine limits output, which is also an answer).
  let bottleneck: Step;
  if (numbers.state !== "done") {
    bottleneck = {
      key: "bottleneck",
      state: "waiting",
      detail: t("bottleneck.waiting"),
      href: "/machines",
      go: t("bottleneck.go"),
    };
  } else if (!found) {
    bottleneck = {
      key: "bottleneck",
      state: "failed",
      detail: t("bottleneck.none"),
      href: "/import",
      go: t("data.goImport"),
    };
  } else {
    bottleneck = {
      key: "bottleneck",
      state: "done",
      detail:
        internal && found.resource_code
          ? t("bottleneck.found", {
              machine: label(found.resource_code),
              level: t(`level.${found.confidence}`),
            })
          : t(`bottleneck.${found.kind}`, { level: t(`level.${found.confidence}`) }),
      href: "/machines",
      go: t("bottleneck.go"),
    };
  }

  // 4. Cost calculated: euros, or hours and what adds euros, or nothing to cost.
  const total = loss.data?.facts.find(
    (f) => f.measure === "lost_eur_cents" && f.reason_code === "total",
  );
  let cost: Step;
  if (bottleneck.state !== "done") {
    cost = {
      key: "cost",
      state: "waiting",
      detail: t("cost.waiting"),
      href: "/loss",
      go: t("cost.go"),
    };
  } else if (!internal) {
    cost = {
      key: "cost",
      state: "done",
      detail: t("cost.noBottleneck"),
      href: "/main",
      go: t("cost.goOverview"),
    };
  } else if (total && total.figure.unit === "eur_cents" && isMissing(total.figure.value)) {
    cost = {
      key: "cost",
      state: "todo",
      detail: t("cost.noPrices"),
      href: "/import",
      go: t("cost.goPrices"),
    };
  } else if (total) {
    cost = {
      key: "cost",
      state: "done",
      detail: total.figure.unit === "h" ? t("cost.doneHours") : t("cost.done"),
      href: "/loss",
      go: t("cost.go"),
    };
  } else {
    cost = {
      key: "cost",
      state: "running",
      detail: t("numbers.running"),
      href: "/loss",
      go: t("cost.go"),
    };
  }

  const steps = [data, numbers, bottleneck, cost];
  const next = steps.find((s) => s.state !== "done");
  return (
    <div className="flex flex-col gap-4">
      {header}
      <p className="m-0 text-sm">
        {next ? (
          <>
            <span className="font-medium">{t("nextIs", { step: t(`${next.key}.title`) })}</span>{" "}
            <Link href={next.href}>{next.go}</Link>
          </>
        ) : (
          <>
            <span className="font-medium">{t("allDone")}</span>{" "}
            <Link href="/main">{t("toOverview")}</Link>
          </>
        )}
      </p>
      <ol aria-label={t("stepsLabel")} className="m-0 flex list-none flex-col gap-0 p-0">
        {steps.map((s, i) => {
          const g = GLYPH[s.state];
          const current = s === next;
          return (
            <li
              key={s.key}
              aria-current={current ? "step" : undefined}
              className={`flex gap-4 border border-line p-4 ${i > 0 ? "-mt-px" : ""} ${current ? "border-accent bg-raised" : "bg-surface"}`}
            >
              <span aria-hidden="true" className={`w-5 text-lg ${g.colour}`}>
                {g.glyph}
              </span>
              <div className="flex flex-1 flex-col gap-1">
                <div className="flex flex-wrap items-baseline gap-3">
                  <h2 className="m-0 text-base font-medium">
                    <span data-raw>{t("stepNo", { n: i + 1 })}</span> {t(`${s.key}.title`)}
                  </h2>
                  <MicroLabel>{t(`state.${s.state}`)}</MicroLabel>
                </div>
                <p className="m-0 text-sm text-muted" data-raw>
                  {s.detail}
                </p>
              </div>
              {s.state !== "waiting" && (
                <Link href={s.href} className="self-center text-sm">
                  {s.go}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
