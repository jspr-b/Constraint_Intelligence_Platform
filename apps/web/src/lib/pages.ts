import {
  BadgeEuro,
  CalendarClock,
  CalendarDays,
  CalendarRange,
  Cpu,
  Factory,
  FileText,
  KeyRound,
  Layers,
  LayoutDashboard,
  ListChecks,
  Monitor,
  MonitorPlay,
  Play,
  Plug,
  ShieldCheck,
  TrendingDown,
  Upload,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";

/** Page keys match the API's access model (cip_api.auth.roles.PAGES). */
export const PAGE_KEYS = [
  "run",
  "data",
  "main",
  "loss",
  "machines",
  "actions",
  "report",
  "planner",
  "buffer",
  "plan",
  "flow",
  "shift",
  "station",
  "value",
  "import",
  "setup",
  "calendar",
  "access",
  "users",
  "conn",
] as const;
export type PageKey = (typeof PAGE_KEYS)[number];

export type GroupKey = "diagnose" | "plan" | "operate" | "prove" | "setup";

/** Which festival builds the page; every page shows 'not built yet' until then. */
export type BuiltBy = "foundation" | "diagnose" | "plan" | "operate" | "prove";

export interface PageDef {
  key: PageKey;
  icon: LucideIcon;
  builtBy: BuiltBy;
}

export const GROUPS: { key: GroupKey; pages: PageDef[] }[] = [
  {
    key: "diagnose",
    pages: [
      { key: "run", icon: Play, builtBy: "diagnose" },
      { key: "data", icon: ShieldCheck, builtBy: "foundation" },
      { key: "main", icon: LayoutDashboard, builtBy: "diagnose" },
      { key: "loss", icon: TrendingDown, builtBy: "diagnose" },
      { key: "machines", icon: Cpu, builtBy: "diagnose" },
      { key: "actions", icon: ListChecks, builtBy: "diagnose" },
      { key: "report", icon: FileText, builtBy: "diagnose" },
    ],
  },
  {
    key: "plan",
    pages: [
      { key: "planner", icon: CalendarClock, builtBy: "plan" },
      { key: "buffer", icon: Layers, builtBy: "plan" },
      { key: "plan", icon: CalendarRange, builtBy: "plan" },
    ],
  },
  {
    key: "operate",
    pages: [
      { key: "flow", icon: Workflow, builtBy: "operate" },
      { key: "shift", icon: MonitorPlay, builtBy: "operate" },
      { key: "station", icon: Monitor, builtBy: "operate" },
    ],
  },
  { key: "prove", pages: [{ key: "value", icon: BadgeEuro, builtBy: "prove" }] },
  {
    key: "setup",
    pages: [
      { key: "import", icon: Upload, builtBy: "foundation" },
      { key: "setup", icon: Factory, builtBy: "foundation" },
      { key: "calendar", icon: CalendarDays, builtBy: "foundation" },
      { key: "access", icon: KeyRound, builtBy: "foundation" },
      { key: "users", icon: Users, builtBy: "foundation" },
      { key: "conn", icon: Plug, builtBy: "foundation" },
    ],
  },
];

export const PAGES: Record<PageKey, PageDef> = Object.fromEntries(
  GROUPS.flatMap((g) => g.pages).map((p) => [p.key, p]),
) as Record<PageKey, PageDef>;

export function groupOf(page: PageKey): GroupKey {
  return GROUPS.find((g) => g.pages.some((p) => p.key === page))?.key ?? "diagnose";
}

export function isPageKey(value: string): value is PageKey {
  return (PAGE_KEYS as readonly string[]).includes(value);
}

export const ROLES = ["plant_director", "coo", "planner", "shift_lead", "station", "it"] as const;
export type Role = (typeof ROLES)[number];

export function isRole(value: string | undefined): value is Role {
  return value !== undefined && (ROLES as readonly string[]).includes(value);
}
