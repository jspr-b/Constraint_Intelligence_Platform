"use client";

import { createContext, use, useState, type ReactNode } from "react";

interface DetailsApi {
  content: ReactNode | null;
  /** Show this in the Details panel and open the panel. */
  show: (content: ReactNode) => void;
  clear: () => void;
  open: boolean;
  setOpen: (open: boolean) => void;
}

const DetailsContext = createContext<DetailsApi>({
  content: null,
  show: () => undefined,
  clear: () => undefined,
  open: true,
  setOpen: () => undefined,
});

/** What the right Details panel shows; pages put item details here (e.g. how a number is made). */
export function DetailsProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState<ReactNode | null>(null);
  const [open, setOpen] = useState(true);
  const show = (next: ReactNode) => {
    setContent(next);
    setOpen(true);
  };
  return (
    <DetailsContext value={{ content, show, clear: () => setContent(null), open, setOpen }}>
      {children}
    </DetailsContext>
  );
}

export function useDetails(): DetailsApi {
  return use(DetailsContext);
}
