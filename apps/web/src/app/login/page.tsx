import { cookies } from "next/headers";
import { getTranslations } from "next-intl/server";
import { EmptyState } from "@/components/EmptyState";
import { ThemeToggle } from "@/components/HeaderControls";
import { LoginForm } from "@/components/LoginForm";
import { THEME_COOKIE, isTheme } from "@/lib/prefs";
import { signInTenant } from "@/lib/tenant";

/** Sign-in: personal (company account, or email in dev pilots) and station (machine + PIN). */
export default async function Login({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const t = await getTranslations();
  const tenant = signInTenant();
  const stored = (await cookies()).get(THEME_COOKIE)?.value;
  const { error } = await searchParams;
  return (
    <main
      id="content"
      className="flex min-h-screen flex-col items-center justify-center px-4 py-10"
    >
      <div className="flex w-full max-w-110 flex-col gap-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="font-mono text-xs font-medium tracking-[0.12em] uppercase">
            {t("app.name")}
          </span>
          <div className="flex gap-2">
            <ThemeToggle initial={isTheme(stored) ? stored : "white"} />
          </div>
        </div>
        {tenant ? (
          <LoginForm tenantId={tenant} ssoError={error === "sso"} />
        ) : (
          <EmptyState title={t("login.title")}>{t("login.noTenant")}</EmptyState>
        )}
        <span className="text-center text-xs text-muted">{t("login.foot")}</span>
      </div>
    </main>
  );
}
