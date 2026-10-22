"use client";

import { PageCrash } from "@/components/PageCrash";

/** A crash inside one page; the shell and menu stay usable. */
export default function PageError(props: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return <PageCrash {...props} />;
}
