"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useView } from "@/components/ViewContext";

/** "/" opens the role's start page. */
export default function Home() {
  const view = useView();
  const router = useRouter();
  useEffect(() => {
    if (view) router.replace(`/${view.startPage}`);
  }, [view, router]);
  return null;
}
