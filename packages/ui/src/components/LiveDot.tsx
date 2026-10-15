/** Pulsing dot on live panels. The pulse stops under prefers-reduced-motion. */
export function LiveDot() {
  return (
    <span
      aria-hidden="true"
      data-live-dot=""
      className="inline-block size-1.5 rounded-full bg-ok motion-safe:animate-live"
    />
  );
}
