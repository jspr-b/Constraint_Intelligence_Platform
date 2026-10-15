import { useId, type ReactNode } from "react";
import { MicroLabel } from "./MicroLabel";

export interface PanelProps {
  /** Micro label on the left of the header strip, e.g. "PAINT LINE". */
  label: string;
  /** Right side of the header strip: a live UTC timestamp or a status. */
  status?: ReactNode;
  children?: ReactNode;
  className?: string;
}

/** Panel with a header strip: micro label left, timestamp or status right. Hairlines, no shadow. */
export function Panel({ label, status, children, className = "" }: PanelProps) {
  const id = useId();
  return (
    <section
      aria-labelledby={id}
      className={`min-w-0 rounded-panel border border-line bg-surface ${className}`}
    >
      <header className="flex min-h-9 flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
        <h2 id={id} className="m-0">
          <MicroLabel>{label}</MicroLabel>
        </h2>
        {status !== undefined && (
          <span className="flex items-center gap-2 font-mono text-xs text-muted">{status}</span>
        )}
      </header>
      {/* Wide tables scroll inside the panel instead of overflowing onto neighbours. */}
      <div className="overflow-x-auto p-3">{children}</div>
    </section>
  );
}
