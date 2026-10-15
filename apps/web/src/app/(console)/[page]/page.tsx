import { notFound } from "next/navigation";
import { PageView } from "@/components/PageView";
import { PAGE_KEYS, isPageKey } from "@/lib/pages";

/** Only the known pages exist; anything else is a 404. */
export const dynamicParams = false;

export function generateStaticParams() {
  return PAGE_KEYS.map((page) => ({ page }));
}

export default async function Page({ params }: { params: Promise<{ page: string }> }) {
  const { page } = await params;
  if (!isPageKey(page)) notFound();
  return <PageView page={page} />;
}
