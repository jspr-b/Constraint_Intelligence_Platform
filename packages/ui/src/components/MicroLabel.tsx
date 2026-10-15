import type { ReactNode } from "react";

/** Uppercase micro label: 10-11 px, tracked, muted. For section tags and status codes. */
export function MicroLabel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted ${className}`}
    >
      {children}
    </span>
  );
}
