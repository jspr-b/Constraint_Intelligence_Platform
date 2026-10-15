import type { Page } from "@playwright/test";

/** Mirrors the API defaults (ADR-0007): every page allowed, start page per role. */
export const PAGES = [
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
];
export const START: Record<string, string> = {
  plant_director: "main",
  coo: "main",
  planner: "planner",
  shift_lead: "shift",
  station: "station",
  it: "conn",
};

export interface Stub {
  role?: string;
  /** Pages per role in the COO's access matrix; default all. */
  pages?: Partial<Record<string, string[]>>;
}

/** Stub the platform API in the browser: signed in as `role`, with the given access matrix. */
export async function stubApi(page: Page, stub: Stub = {}): Promise<void> {
  const role = stub.role ?? "coo";
  const pagesOf = (r: string) => stub.pages?.[r] ?? PAGES;
  await page.route("**/api/health", (route) =>
    route.fulfill({ json: { status: "ok", db: "ok", redis: "ok" } }),
  );
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      json: {
        tenant_id: "00000000-0000-0000-0000-0000000000a1",
        subject_type: "user",
        subject_id: "00000000-0000-0000-0000-0000000000b1",
        role,
        plant_code: null,
        resource_code: null,
        start_page: START[role],
        pages: pagesOf(role),
        money: "eur",
        plants: "all",
        decisions: [],
      },
    }),
  );
  await page.route("**/api/access", (route) =>
    route.fulfill({
      json: {
        pages: PAGES,
        decisions: [],
        roles: Object.keys(START).map((r) => ({
          role: r,
          start_page: START[r],
          pages: pagesOf(r),
          money: "eur",
          plants: "all",
          decisions: [],
        })),
        locked_pages: {},
        locked_decisions: [],
      },
    }),
  );
}
