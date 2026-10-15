"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import {
  Button,
  Menu,
  MenuItem,
  MenuTrigger,
  Popover,
  Header,
  MenuSection,
} from "react-aria-components";
import { LOCALES, LOCALE_COOKIE } from "@/i18n/locales";
import { api } from "@/lib/api/client";
import { THEME_COOKIE, VIEW_AS_COOKIE, applyTheme, setPref, type Theme } from "@/lib/prefs";
import { ROLES, type Role } from "@/lib/pages";
import type { AccessMatrix } from "@/lib/session";

const SEGMENT =
  "min-h-7 cursor-pointer border-0 bg-transparent px-2.5 text-xs text-muted outline-none " +
  "aria-pressed:bg-accent aria-pressed:text-on-accent focus-visible:outline-1 focus-visible:outline-accent";

export function ThemeToggle({ initial }: { initial: Theme }) {
  const t = useTranslations("header");
  const [theme, setTheme] = useState<Theme>(initial);
  const choose = (next: Theme) => {
    setTheme(next);
    setPref(THEME_COOKIE, next);
    applyTheme(next);
  };
  return (
    <div
      role="group"
      aria-label={t("theme")}
      className="flex rounded-control border border-line-strong"
    >
      {(["white", "dark"] as const).map((option) => (
        <button
          key={option}
          type="button"
          className={SEGMENT}
          aria-pressed={theme === option}
          onClick={() => choose(option)}
        >
          {t(option)}
        </button>
      ))}
    </div>
  );
}

export function LocaleSwitch() {
  const t = useTranslations("header");
  const locale = useLocale();
  const router = useRouter();
  return (
    <div
      role="group"
      aria-label={t("language")}
      className="flex rounded-control border border-line-strong"
    >
      {LOCALES.map((option) => (
        <button
          key={option}
          type="button"
          lang={option}
          className={`${SEGMENT} font-mono uppercase`}
          aria-pressed={locale === option}
          onClick={() => {
            setPref(LOCALE_COOKIE, option);
            router.refresh();
          }}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

export function RoleSwitch({ role, matrix }: { role: Role; matrix: AccessMatrix }) {
  const t = useTranslations();
  const router = useRouter();
  const queries = useQueryClient();
  const open = (next: Role) => {
    setPref(VIEW_AS_COOKIE, next);
    const start = matrix.roles.find((r) => r.role === next)?.start_page ?? "main";
    void queries.invalidateQueries();
    router.push(`/${start}`);
    router.refresh();
  };
  return (
    <MenuTrigger>
      <Button className="inline-flex min-h-7 cursor-pointer items-center gap-1 rounded-control border border-line-strong bg-transparent px-2 font-mono text-xs text-accent outline-none data-[focus-visible]:outline-1 data-[focus-visible]:outline-accent">
        {t("header.role")}: {t(`roles.${role}`)}
        <ChevronDown aria-hidden="true" size={14} strokeWidth={1.5} />
      </Button>
      <Popover
        placement="bottom end"
        className="min-w-60 rounded-panel border border-line-strong bg-surface p-1.5"
      >
        <Menu
          aria-label={t("header.role")}
          className="outline-none"
          selectionMode="single"
          selectedKeys={[role]}
          onAction={(key) => open(String(key) as Role)}
        >
          <MenuSection>
            <Header className="px-2.5 pt-1.5 pb-1 text-micro font-medium uppercase tracking-[var(--tracking-micro)] text-muted">
              {t("header.roleSwitchHint")}
            </Header>
            {ROLES.map((option) => (
              <MenuItem
                key={option}
                id={option}
                className="cursor-pointer rounded-control px-2.5 py-2 text-sm text-text outline-none data-[focused]:bg-raised data-[selected]:text-accent"
              >
                {t(`roles.${option}`)}
              </MenuItem>
            ))}
          </MenuSection>
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}

export function SignOut() {
  const t = useTranslations("login");
  const router = useRouter();
  const queries = useQueryClient();
  return (
    <button
      type="button"
      className="min-h-7 cursor-pointer rounded-control border border-line-strong bg-transparent px-2.5 text-xs text-muted hover:bg-raised hover:text-text focus-visible:outline-1 focus-visible:outline-accent"
      onClick={async () => {
        await api.POST("/auth/logout");
        queries.clear();
        router.replace("/login");
      }}
    >
      {t("signOut")}
    </button>
  );
}
