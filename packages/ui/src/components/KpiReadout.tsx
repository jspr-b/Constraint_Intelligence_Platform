"use client";

import type { ReactNode } from "react";
import { FigureTooltip } from "./FigureTooltip";
import { MicroLabel } from "./MicroLabel";
import { formatFigure, isMissing, type FigureLike } from "./figure";

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
      <FigureTooltip
        figure={figure}
        formulaText={formulaText}
        confidenceLabel={confidenceLabel}
        className="self-start"
      >
        {missing ? (
          <span className="font-display text-2xl font-bold leading-none text-faint">
            {missingLabel}
          </span>
        ) : (
          <span className="font-display text-2xl font-bold leading-none text-text">
            {formatFigure(figure, locale)}
          </span>
        )}
      </FigureTooltip>
      {(delta !== undefined || impact !== undefined) && (
        <div className="flex flex-wrap gap-3 font-mono text-xs text-muted">
          {delta !== undefined && <span>{delta}</span>}
          {impact !== undefined && <span>{impact}</span>}
        </div>
      )}
    </div>
  );
}
