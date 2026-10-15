import { getTranslations } from "next-intl/server";
import { EmptyState } from "@/components/EmptyState";
import { LocaleSwitch } from "@/components/HeaderControls";

/** Sign-in page: built in the foundation pages sequence (personal and station tabs). */
export default async function Login() {
  const t = await getTranslations();
  return (
    <main id="content" className="mx-auto flex max-w-lg flex-col gap-4 p-8">
      <div className="flex items-center justify-between">
        <h1 className="m-0 text-xl font-medium">{t("login.title")}</h1>
        <LocaleSwitch />
      </div>
      <EmptyState title={t("empty.notBuilt")}>{t("empty.builtBy.foundation")}</EmptyState>
    </main>
  );
}
