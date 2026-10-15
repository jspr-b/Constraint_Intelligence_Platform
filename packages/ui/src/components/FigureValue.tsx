"use client";

import { formatFigure, isMissing, type FigureLike } from "./figure";
import { FigureTooltip } from "./FigureTooltip";

/** An engine number inline (tables, sentences), with its formula on hover/focus. */
export function FigureValue({
  figure,
  locale = "en",
  missingLabel = "Missing",
  confidenceLabel,
  formulaText,
}: {
  figure: FigureLike;
  locale?: string;
  missingLabel?: string;
  confidenceLabel?: string;
  formulaText?: string;
}) {
  const missing = isMissing(figure.value);
  return (
    <FigureTooltip
      figure={figure}
      formulaText={formulaText}
      {...(confidenceLabel ? { confidenceLabel } : {})}
      className="font-mono underline decoration-line-strong decoration-dotted underline-offset-4"
    >
      <span className={missing ? "text-faint" : "text-text"}>
        {missing ? missingLabel : formatFigure(figure, locale)}
      </span>
    </FigureTooltip>
  );
}
