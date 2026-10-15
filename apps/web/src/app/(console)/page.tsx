"use client";

import { redirect } from "next/navigation";
import { useView } from "@/components/ViewContext";

/** "/" opens the role's start page. */
export default function Home() {
  const view = useView();
  if (view) redirect(`/${view.startPage}`);
  return null;
}
