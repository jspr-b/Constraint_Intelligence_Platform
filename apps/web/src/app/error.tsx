"use client";

import { PageCrash } from "@/components/PageCrash";

/** A crash outside the console pages (sign-in, shift TV). */
export default function RootError(props: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <main id="content" className="mx-auto max-w-lg p-8">
      <PageCrash {...props} />
    </main>
  );
}
