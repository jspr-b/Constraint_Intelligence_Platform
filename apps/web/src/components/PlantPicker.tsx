"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { api } from "@/lib/api/client";
import { Field } from "./FormDialog";
import { EmptyState } from "./EmptyState";

/** The plants this role may see; remembers the choice for the session. */
export function usePlant(): {
  plants: { plant_code: string; name: string }[] | undefined;
  plant: string | null;
  setPlant: (code: string) => void;
} {
  const query = useQuery({
    queryKey: ["plants"],
    queryFn: async () => (await api.GET("/plants")).data ?? [],
  });
  const [chosen, setPlant] = useState<string | null>(null);
  const plant = chosen ?? query.data?.[0]?.plant_code ?? null;
  return { plants: query.data, plant, setPlant };
}

export function PlantPicker({ plants, plant, setPlant }: ReturnType<typeof usePlant>) {
  const t = useTranslations("plant");
  if (plants && plants.length === 0) {
    return (
      <EmptyState title={t("none")}>
        {t("noneBody")} <Link href="/setup">{t("toSetup")}</Link>
      </EmptyState>
    );
  }
  return (
    <Field label={t("label")} className="flex items-center gap-2">
      {(id) => (
        <select
          id={id}
          value={plant ?? ""}
          onChange={(e) => setPlant(e.target.value)}
          className="min-h-8 rounded-control border border-line-strong bg-surface px-2 text-sm text-text"
        >
          {(plants ?? []).map((p) => (
            <option key={p.plant_code} value={p.plant_code}>
              {p.plant_code} · {p.name}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}
