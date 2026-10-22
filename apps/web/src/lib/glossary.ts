/** Glossary words (messages `glossary.terms.<key>`), in the order the glossary lists them. */
export const TERMS = [
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
