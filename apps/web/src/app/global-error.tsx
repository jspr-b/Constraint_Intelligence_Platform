"use client";

import Link from "next/link";
import "./globals.css";
import messages from "../../messages/en.json";

const t = messages.problems;

/** The root layout itself failed: no providers here, so the English messages are read directly. */
export default function GlobalError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <html lang="en" data-theme="white">
      <body className="m-0 min-h-screen bg-bg text-text">
        <main role="alert" className="mx-auto flex max-w-lg flex-col gap-3 p-8 text-sm">
          <title>{t.pageTitle}</title>
          <h1 className="m-0 text-base font-medium">{t.pageTitle}</h1>
          <p className="m-0 text-muted">{t.pageBody}</p>
          <div className="flex gap-3">
            <button type="button" onClick={retry}>
              {t.tryAgain}
            </button>
            <Link href="/">{t.home}</Link>
          </div>
          <details className="text-xs text-muted">
            <summary>{t.details}</summary>
            <p className="font-mono">
              {error.message}
              {error.digest ? ` · ${t.reference.replace("{digest}", error.digest)}` : ""}
            </p>
          </details>
        </main>
      </body>
    </html>
  );
}
