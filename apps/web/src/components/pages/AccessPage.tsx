"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Tab, TabList, TabPanel, Tabs } from "react-aria-components";
import { Button, MicroLabel, Panel } from "@cip/ui";
import { api, ensureOk } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { GROUPS, ROLES, type Role } from "@/lib/pages";
import { Count } from "../Figure";
import { PageHeader } from "../PageHeader";
import { ReadOnlyNote } from "../ReadOnlyNote";
import { useView } from "../ViewContext";

type Matrix = components["schemas"]["AccessOut"];
type Decision = components["schemas"]["Decision"];

const TAB =
  "min-h-10 cursor-pointer border-b-2 border-transparent px-3.5 text-sm text-muted outline-none data-[selected]:border-accent data-[selected]:text-text data-[focus-visible]:outline-1 data-[focus-visible]:outline-accent";
const TH =
  "px-2 py-2 text-left text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted";
const BOX = "size-4 accent-[var(--accent)] disabled:cursor-not-allowed";

/** Access page (mockup F3): pages, data and decisions per role. Only the COO changes them. */
export function AccessPage() {
  const t = useTranslations("access");
  const tf = useTranslations("figure");
  const tn = useTranslations("nav");
  const tr = useTranslations("roles");
  const view = useView();
  const queries = useQueryClient();
  const canChange = (view?.decisions.has("change_access") ?? false) && view?.preview === false;
  const matrix = useQuery({
    queryKey: ["access"],
    queryFn: async () => (await api.GET("/access")).data ?? null,
  });
  const save = useMutation({
    mutationFn: async (call: () => Promise<{ data?: Matrix; response: Response }>) =>
      (await ensureOk(call())).data,
    onSuccess: (data) => {
      if (data) queries.setQueryData(["access"], data);
      void queries.invalidateQueries({ queryKey: ["me"] });
    },
    // Undo the optimistic change: show what the server really has.
    onError: () => void queries.invalidateQueries({ queryKey: ["access"] }),
  });
  /** Show the change at once; the server's answer then replaces it (or restores on error). */
  const optimistic = (role: Role, field: "pages" | "decisions", item: string, allowed: boolean) =>
    queries.setQueryData<Matrix | null>(["access"], (old) =>
      old
        ? {
            ...old,
            roles: old.roles.map((r) =>
              r.role !== role
                ? r
                : {
                    ...r,
                    [field]: allowed
                      ? [...r[field], item]
                      : (r[field] as string[]).filter((x) => x !== item),
                  },
            ),
          }
        : old,
    );
  const m = matrix.data;
  if (!m) return <PageHeader page="access" />;
  const byRole = Object.fromEntries(m.roles.map((r) => [r.role, r])) as Record<
    Role,
    Matrix["roles"][number]
  >;
  const restricted = m.roles.reduce((n, r) => n + (m.pages.length - r.pages.length), 0);
  const locked = (role: Role, page: string) => (m.locked_pages[role] ?? []).includes(page);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        page="access"
        headline={
          restricted === 0 ? t("headlineAll") : t("headlineRestricted", { count: restricted })
        }
        actions={
          canChange ? (
            <>
              <Button
                onPress={() =>
                  save.mutate(() =>
                    api.POST("/access/presets/{preset}", {
                      params: { path: { preset: "everyone" } },
                    }),
                  )
                }
              >
                {t("presetAll")}
              </Button>
              <Button
                onPress={() =>
                  save.mutate(() =>
                    api.POST("/access/presets/{preset}", {
                      params: { path: { preset: "role_menus" } },
                    }),
                  )
                }
              >
                {t("presetMenus")}
              </Button>
            </>
          ) : undefined
        }
      />
      {!canChange && <ReadOnlyNote decision="change_access" />}
      <ul className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2 xl:grid-cols-3">
        {ROLES.map((role) => (
          <li
            key={role}
            className="flex flex-col gap-1 rounded-panel border border-line bg-surface p-3"
          >
            <span className="text-sm font-medium">{tr(role)}</span>
            <span className="text-sm text-muted">{t(`question.${role}`)}</span>
            <span className="text-xs text-muted">
              {t("startPage")}{" "}
              <Link href={`/${byRole[role].start_page}`} className="text-accent">
                {tn(`pages.${byRole[role].start_page}`)}
              </Link>
            </span>
          </li>
        ))}
      </ul>
      <Panel label={t("label")}>
        <Tabs>
          <TabList aria-label={t("label")} className="flex border-b border-line">
            <Tab id="pages" className={TAB}>
              {t("tabPages")}
            </Tab>
            <Tab id="data" className={TAB}>
              {t("tabData")}
            </Tab>
            <Tab id="decisions" className={TAB}>
              {t("tabDecisions")}
            </Tab>
          </TabList>
          <TabPanel id="pages" className="overflow-x-auto pt-3 outline-none">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr>
                  <th scope="col" className={TH}>
                    {t("page")}
                  </th>
                  {ROLES.map((role) => (
                    <th key={role} scope="col" className={TH}>
                      {tr(role)}
                      <span className="block font-mono normal-case tracking-normal">
                        <Count
                          value={byRole[role].pages.length}
                          label={tr(role)}
                          source={{ what: tf("src.accessPages") }}
                        >
                          {byRole[role].pages.length}/{m.pages.length}
                        </Count>
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {GROUPS.flatMap((g) =>
                  g.pages.map((p, i) => (
                    <tr key={p.key} className="border-t border-line">
                      <th scope="row" className="px-2 py-1.5 text-left font-normal">
                        {i === 0 && (
                          <MicroLabel className="block">{tn(`groups.${g.key}`)}</MicroLabel>
                        )}
                        {tn(`pages.${p.key}`)}
                      </th>
                      {ROLES.map((role) => (
                        <td key={role} className="px-2 py-1.5">
                          <input
                            type="checkbox"
                            className={BOX}
                            aria-label={t("pageFor", {
                              page: tn(`pages.${p.key}`),
                              role: tr(role),
                            })}
                            checked={byRole[role].pages.includes(p.key)}
                            disabled={!canChange || locked(role, p.key)}
                            onChange={(e) => {
                              const allowed = e.target.checked;
                              optimistic(role, "pages", p.key, allowed);
                              save.mutate(() =>
                                api.PUT("/access/pages", {
                                  body: { role, page: p.key, allowed },
                                }),
                              );
                            }}
                          />
                        </td>
                      ))}
                    </tr>
                  )),
                )}
              </tbody>
            </table>
            <p className="m-0 mt-2 text-xs text-muted">{t("lockedNote")}</p>
          </TabPanel>
          <TabPanel id="data" className="overflow-x-auto pt-3 outline-none">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr>
                  <th scope="col" className={TH}>
                    {t("role")}
                  </th>
                  <th scope="col" className={TH}>
                    {t("money")}
                  </th>
                  <th scope="col" className={TH}>
                    {t("plants")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {ROLES.map((role) => {
                  const r = byRole[role];
                  const set = (money: "eur" | "hours", plants: "all" | "own") =>
                    save.mutate(() => api.PUT("/access/data", { body: { role, money, plants } }));
                  return (
                    <tr key={role} className="border-t border-line">
                      <th scope="row" className="px-2 py-1.5 text-left font-normal">
                        {tr(role)}
                      </th>
                      <td className="px-2 py-1.5">
                        <select
                          aria-label={t("moneyFor", { role: tr(role) })}
                          value={r.money}
                          disabled={!canChange}
                          onChange={(e) => set(e.target.value as "eur" | "hours", r.plants)}
                          className="min-h-8 rounded-control border border-line-strong bg-surface px-2 text-sm text-text"
                        >
                          <option value="eur">{t("moneyEur")}</option>
                          <option value="hours">{t("moneyHours")}</option>
                        </select>
                      </td>
                      <td className="px-2 py-1.5">
                        <select
                          aria-label={t("plantsFor", { role: tr(role) })}
                          value={r.plants}
                          disabled={!canChange}
                          onChange={(e) => set(r.money, e.target.value as "all" | "own")}
                          className="min-h-8 rounded-control border border-line-strong bg-surface px-2 text-sm text-text"
                        >
                          <option value="all">{t("plantsAll")}</option>
                          <option value="own">{t("plantsOwn")}</option>
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="m-0 mt-2 text-xs text-muted">{t("hoursNote")}</p>
          </TabPanel>
          <TabPanel id="decisions" className="overflow-x-auto pt-3 outline-none">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr>
                  <th scope="col" className={TH}>
                    {t("decision")}
                  </th>
                  {ROLES.map((role) => (
                    <th key={role} scope="col" className={TH}>
                      {tr(role)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {m.decisions.map((d: Decision) => (
                  <tr key={d} className="border-t border-line">
                    <th scope="row" className="px-2 py-1.5 text-left font-normal">
                      {t(`decisions.${d}`)}
                      {m.locked_decisions.includes(d) && (
                        <span className="ml-2 text-xs text-muted">{t("lockedDecision")}</span>
                      )}
                    </th>
                    {ROLES.map((role) => (
                      <td key={role} className="px-2 py-1.5">
                        <input
                          type="checkbox"
                          className={BOX}
                          aria-label={t("decisionFor", {
                            decision: t(`decisions.${d}`),
                            role: tr(role),
                          })}
                          checked={byRole[role].decisions.includes(d)}
                          disabled={!canChange || m.locked_decisions.includes(d)}
                          onChange={(e) => {
                            const allowed = e.target.checked;
                            optimistic(role, "decisions", d, allowed);

                            save.mutate(() =>
                              api.PUT("/access/decisions", {
                                body: { role, decision: d, allowed },
                              }),
                            );
                          }}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </TabPanel>
        </Tabs>
      </Panel>
      <p className="m-0 text-xs text-muted">{t("auditNote")}</p>
    </div>
  );
}
