/** Glossary words (messages `glossary.terms.<key>`), in the order the glossary lists them. */
export const TERMS = [
  "step",
  "handmade",
  "positions",
  "team",
  "touchpoint",
  "bottleneck",
  "throughput",
  "capacity",
  "oee",
  "setup",
  "starved",
  "blocked",
  "buffer",
  "confidence",
] as const;
export type TermKey = (typeof TERMS)[number];
