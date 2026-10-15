import { cookies } from "next/headers";
import type { ReactNode } from "react";
import { Shell } from "@/components/Shell";
import { THEME_COOKIE, VIEW_AS_COOKIE, isTheme } from "@/lib/prefs";

export default async function ConsoleLayout({ children }: { children: ReactNode }) {
  const jar = await cookies();
  const stored = jar.get(THEME_COOKIE)?.value;
  return (
    <Shell theme={isTheme(stored) ? stored : "white"} viewAs={jar.get(VIEW_AS_COOKIE)?.value}>
      {children}
    </Shell>
  );
}
