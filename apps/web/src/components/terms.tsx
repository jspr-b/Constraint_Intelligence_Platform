import type { ReactNode } from "react";
import { TERMS, type TermKey } from "@/lib/glossary";
import { Term } from "./Term";

/**
 * Tags for `t.rich`: wrap a word in a message in its term tag (e.g. the bottleneck tag) to
 * explain it inline.
 * Not a client module, so server pages can use it too.
 */
export const termTags = Object.fromEntries(
  TERMS.map((id) => [id, (chunks: ReactNode) => <Term id={id}>{chunks}</Term>]),
) as Record<TermKey, (chunks: ReactNode) => ReactNode>;
