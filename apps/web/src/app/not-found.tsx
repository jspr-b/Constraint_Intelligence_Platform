import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { EmptyState } from "@/components/EmptyState";

export default async function NotFound() {
  const t = await getTranslations("notFound");
  return (
    <main id="content" className="mx-auto max-w-lg p-8">
      <EmptyState title={t("title")}>
        <Link href="/">{t("home")}</Link>
      </EmptyState>
    </main>
  );
}
