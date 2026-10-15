import "./globals.css";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import type { ReactNode } from "react";
import { Providers } from "@/components/Providers";
import { THEME_COOKIE, isTheme } from "@/lib/prefs";

export const metadata: Metadata = {
  title: "Constraint Intelligence",
  description: "What limits your output, what it costs, and where it moves next.",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const locale = await getLocale();
  const stored = (await cookies()).get(THEME_COOKIE)?.value;
  const theme = isTheme(stored) ? stored : "white";
  return (
    <html lang={locale} data-theme={theme}>
      <body className="m-0 min-h-screen bg-bg text-text">
        <NextIntlClientProvider>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
