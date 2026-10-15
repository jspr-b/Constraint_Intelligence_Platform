"use client";

import type { ReactNode } from "react";
import { Button as AriaButton, OverlayArrow, Tooltip, TooltipTrigger } from "react-aria-components";
import { MicroLabel } from "./MicroLabel";
import { formatFigure, isMissing, type FigureLike, type MissingValue } from "./figure";

export interface KpiReadoutProps {
  label: string;
  figure: FigureLike;
  /** Formula text from GET /meta, shown with the formula id. */
  formulaText?: string;
  /** Change versus the previous period, already formatted. */
  delta?: ReactNode;
  /** Slot for the € impact. */
  impact?: ReactNode;
  locale?: string;
  /** Translated word for a missing value. */
  missingLabel?: string;
  /** Translated label before the confidence level. */
  confidenceLabel?: string;
}

/** KPI readout: micro label, large D-DIN numeral, delta and € impact; formula on hover/focus. */
export function KpiReadout({
  label,
  figure,
  formulaText,
  delta,
  impact,
  locale = "en",
  missingLabel = "Missing",
  confidenceLabel = "confidence",
}: KpiReadoutProps) {
  const missing = isMissing(figure.value) ? figure.value : null;
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <MicroLabel>{label}</MicroLabel>
      <TooltipTrigger delay={300} closeDelay={0}>
        <AriaButton className="cursor-help self-start rounded-control text-left outline-none data-[focus-visible]:outline-1 data-[focus-visible]:outline-offset-2 data-[focus-visible]:outline-accent">
          {missing ? (
            <span className="font-display text-2xl font-bold leading-none text-faint">
              {missingLabel}
            </span>
          ) : (
            <span className="font-display text-2xl font-bold leading-none text-text">
              {formatFigure(figure, locale)}
            </span>
          )}
        </AriaButton>
        <Tooltip
          offset={6}
          className="max-w-80 rounded-panel border border-line-strong bg-surface p-3 text-xs text-text"
        >
          <OverlayArrow />
          <p className="m-0 font-mono">{figure.formula_id}</p>
          {formulaText && <p className="m-0 mt-1">{formulaText}</p>}
          {missing && <p className="m-0 mt-1 text-muted">{missing.reason}</p>}
          <dl className="m-0 mt-2 grid grid-cols-[auto_1fr] gap-x-3 font-mono text-micro">
            {Object.entries(figure.inputs).map(([name, input]) => (
              <div key={name} className="contents">
                <dt className="text-muted">{name}</dt>
                <dd className="m-0">{describe(input)}</dd>
              </div>
            ))}
          </dl>
          <p className="m-0 mt-2 text-micro uppercase text-muted">
            {confidenceLabel} {figure.confidence}
          </p>
        </Tooltip>
      </TooltipTrigger>
      {(delta !== undefined || impact !== undefined) && (
        <div className="flex flex-wrap gap-3 font-mono text-xs text-muted">
          {delta !== undefined && <span>{delta}</span>}
          {impact !== undefined && <span>{impact}</span>}
        </div>
      )}
    </div>
  );
}

function describe(input: unknown): string {
  if (input !== null && typeof input === "object") {
    if ("formula_id" in input) {
      const nested = input as FigureLike;
      const shown = isMissing(nested.value) ? "missing" : String(nested.value);
      return `${nested.formula_id} = ${shown} ${nested.unit}`;
    }
    if ("missing" in input) return `missing (${(input as MissingValue).reason})`;
  }
  return String(input);
}
