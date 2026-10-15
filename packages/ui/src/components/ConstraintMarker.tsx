import type { ReactNode } from "react";

export interface ConstraintMarkerProps {
  children: ReactNode;
  /** Tag text; translated by the app. */
  tag?: string;
}

const CORNERS = [
  "-left-1.5 -top-1.5 border-l-2 border-t-2",
  "-right-1.5 -top-1.5 border-r-2 border-t-2",
  "-bottom-1.5 -left-1.5 border-b-2 border-l-2",
  "-bottom-1.5 -right-1.5 border-b-2 border-r-2",
];

/**
 * Target-lock brackets and a CONSTRAINT tag around the constraint resource.
 * This is the only component that uses the constraint colour.
 */
export function ConstraintMarker({ children, tag = "CONSTRAINT" }: ConstraintMarkerProps) {
  return (
    <span data-constraint="" className="relative inline-block">
      {CORNERS.map((corner) => (
        <span
          key={corner}
          aria-hidden="true"
          className={`pointer-events-none absolute size-2.5 border-constraint ${corner}`}
        />
      ))}
      <span className="absolute -top-5 left-0 rounded-control border border-constraint px-1.5 font-mono text-micro tracking-[var(--tracking-micro)] text-constraint">
        {tag}
      </span>
      {children}
    </span>
  );
}
