import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { MicroLabel } from "@cip/ui";

/** Floor TV mode: one large signal per shift, no menu. Built with the Operate pillar. */
export default async function ShiftTv() {
  const t = await getTranslations();
  return (
    <main id="content" className="flex min-h-screen flex-col gap-6 p-10">
      <div className="flex items-center justify-between">
        <MicroLabel>{t("tv.title")}</MicroLabel>
        <Link href="/shift" className="text-sm text-accent">
          {t("tv.exit")}
        </Link>
      </div>
      <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
        <p className="m-0 font-display text-3xl font-bold text-faint">{t("empty.notBuilt")}</p>
        <p className="m-0 text-base text-muted">{t("empty.builtBy.operate")}</p>
      </div>
    </main>
  );
}
