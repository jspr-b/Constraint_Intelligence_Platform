"use client";

import type { ReactNode } from "react";
import { Button as AriaButton, OverlayArrow, Tooltip, TooltipTrigger } from "react-aria-components";
import { isMissing, type FigureLike, type MissingValue } from "./figure";

/** A focusable trigger that shows a Figure's formula, inputs and confidence on hover/focus. */
export function FigureTooltip({
  figure,
  formulaText,
  confidenceLabel = "confidence",
  className = "",
  children,
}: {
  figure: FigureLike;
  formulaText?: string | undefined;
  confidenceLabel?: string;
  className?: string;
  children: ReactNode;
}) {
  const missing = isMissing(figure.value) ? figure.value : null;
  return (
    <TooltipTrigger delay={300} closeDelay={0}>
      <AriaButton
        className={`cursor-help rounded-control text-left outline-none data-[focus-visible]:outline-1 data-[focus-visible]:outline-offset-2 data-[focus-visible]:outline-accent ${className}`}
      >
        {children}
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
