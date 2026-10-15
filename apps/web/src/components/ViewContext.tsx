"use client";

import { createContext, use } from "react";
import type { View } from "@/lib/session";

export const ViewContext = createContext<View | null>(null);

export function useView(): View | null {
  return use(ViewContext);
}
