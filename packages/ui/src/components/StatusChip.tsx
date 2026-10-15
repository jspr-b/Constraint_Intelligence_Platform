/** The six resource states (cip_schema ResourceState). */
export type ResourceState = "running" | "idle" | "starved" | "blocked" | "down" | "setup";

/** Glyph and colour per state. Status is never colour alone: the glyph and label always show. */
export const STATE_STYLE: Record<ResourceState, { glyph: string; colour: string }> = {
  running: { glyph: "●", colour: "text-ok" },
  idle: { glyph: "○", colour: "text-idle" },
  starved: { glyph: "◐", colour: "text-warn" },
  blocked: { glyph: "■", colour: "text-warn" },
  down: { glyph: "✕", colour: "text-bad" },
  setup: { glyph: "◆", colour: "text-muted" },
};

export interface StatusChipProps {
  state: ResourceState;
  /** Translated label; defaults to the state code in capitals (e.g. STARVED). */
  label?: string;
}

/** Status chip: coloured glyph plus a label in text colour. The only pill shape allowed. */
export function StatusChip({ state, label }: StatusChipProps) {
  const style = STATE_STYLE[state];
  return (
    <span
      data-state={state}
      className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-2 py-px font-mono text-micro uppercase tracking-[var(--tracking-micro)] text-text"
    >
      <span aria-hidden="true" className={style.colour}>
        {style.glyph}
      </span>
      {label ?? state.toUpperCase()}
    </span>
  );
}
