import type { ReactNode } from "react";
import { MicroLabel } from "@cip/ui";

/** Honest empty state: says what is missing, never shows placeholder numbers. */
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex min-h-64 flex-col items-start justify-center gap-2 rounded-panel border border-dashed border-line-strong p-8">
      <MicroLabel>{title}</MicroLabel>
      <div className="max-w-prose text-sm text-muted">{children}</div>
    </div>
  );
}
