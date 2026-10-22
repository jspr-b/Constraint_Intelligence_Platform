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

/** ADR-0007 default decisions per role. */
export const DECISIONS: Record<string, string[]> = {
  plant_director: ["accept_exploit_subordinate", "approve_elevate", "sign_off_value"],
  coo: ["accept_exploit_subordinate", "approve_elevate", "sign_off_value", "change_access"],
  planner: [
    "accept_exploit_subordinate",
    "release_expedite",
    "edit_setup_calendar",
    "import_run_diagnostic",
  ],
  shift_lead: ["release_expedite", "report_stop"],
  station: ["report_stop"],
  it: ["edit_setup_calendar", "import_run_diagnostic", "manage_logins"],
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
        decisions: DECISIONS[role],
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
          decisions: DECISIONS[r],
        })),
        locked_pages: {},
        locked_decisions: [],
      },
    }),
  );
}

const FIG = (value: number, unit: string, formula_id: string) => ({
  value,
  unit,
  formula_id,
  inputs: { sample: 1 },
  period_start_at: null,
  period_end_at: null,
  confidence: "high",
});

/** Synthetic page data for the built foundation pages (accessibility checks see full tables). */
export async function stubPages(
  page: Page,
  overrides: { latestImport?: Record<string, unknown> } = {},
): Promise<void> {
  const plant = {
    plant_code: "PLANT-A",
    name: "Plant A (synthetic)",
    timezone_iana: "Europe/Amsterdam",
  };
  await page.route("**/api/plants", (route) => route.fulfill({ json: [plant] }));
  await page.route("**/api/meta", (route) =>
    route.fulfill({ json: { version: "0.0.0", env: "dev", formulas: [] } }),
  );
  await page.route("**/api/auth/config?*", (route) =>
    route.fulfill({ json: { provider: "dev", tenant_name: "A" } }),
  );
  await page.route("**/api/users", (route) =>
    route.fulfill({
      json: {
        users: [
          {
            user_id: "u1",
            email: "planner@plant-a.example.test",
            role: "planner",
            plant_code: null,
            status: "active",
          },
        ],
        station_logins: [
          {
            station_login_id: "s1",
            plant_code: "PLANT-A",
            resource_code: "PNT-01",
            status: "active",
          },
        ],
      },
    }),
  );
  await page.route("**/api/plants/PLANT-A/resources", (route) =>
    route.fulfill({
      json: [
        {
          resource_code: "PNT-01",
          name: "Paint line",
          kind: "machine",
          station_code: "PAINT",
          parallel_units: 1,
        },
      ],
    }),
  );
  await page.route("**/api/plants/PLANT-A/imports", (route) =>
    route.fulfill({
      json: [
        {
          import_id: "i1",
          plant_code: "PLANT-A",
          status: "done",
          created_at: "2026-10-13T07:15:00Z",
          files: [
            {
              name: "mes_events.csv",
              size_bytes: 1000,
              recognised_as: "mes_events",
              feeds: ["events"],
              readable: true,
              problem: null,
              encoding: "utf-8",
              delimiter: ";",
              columns: 3,
              header: ["Werkplek", "Status", "Medewerker"],
              personal_columns: ["Medewerker"],
              rows: 10,
              preview: [{ Werkplek: "LAK1", Status: "GESTART" }],
            },
            {
              name: "notes.csv",
              size_bytes: 10,
              recognised_as: null,
              feeds: [],
              readable: false,
              problem: "single_column",
              encoding: "utf-8",
              delimiter: ";",
              columns: 1,
              header: ["notes"],
              personal_columns: [],
              rows: 1,
              preview: [],
            },
          ],
          expected_files: [
            "werkplekken",
            "artikelen",
            "bewerkingen",
            "orders",
            "mes_events",
            "rooster",
          ],
          needed: [
            { key: "orders", sources: ["orders"], present: false },
            { key: "events", sources: ["mes_events"], present: true },
          ],
          mapping: "GENERIC-NL",
          sources: [
            {
              source: "mes_events",
              targets: ["events"],
              file: "mes_events.csv",
              readable: true,
              missing_columns: [],
              columns: [
                {
                  name: "Werkplek",
                  status: "mapped",
                  fields: ["events.resource_code"],
                  example: "LAK1",
                  conversions: ["code_table:resource"],
                },
                {
                  name: "Medewerker",
                  status: "not_imported",
                  fields: [],
                  example: null,
                  conversions: [],
                },
              ],
            },
          ],
          report: {
            import: {
              rows_read: { mes_events: 10 },
              rows_written: { events: 9 },
              row_errors: [
                { file: "mes_events.csv", line: 4, reason: "unknown resource code LAS9" },
              ],
              dropped_columns: { mes_events: ["Medewerker"] },
            },
            checklist: [
              {
                number: 12,
                data: "Operation events",
                need: "Must",
                status: "ok",
                detail: "12 weeks",
              },
            ],
          },
          minimum_set: [{ key: "events", numbers: [12], status: "ok" }],
          error: null,
          failed_step: null,
          ...overrides.latestImport,
        },
      ],
    }),
  );
  await page.route("**/api/plants/PLANT-A/setup", (route) =>
    route.fulfill({
      json: {
        plant_code: "PLANT-A",
        name: plant.name,
        timezone_iana: plant.timezone_iana,
        stations: [
          {
            station_code: "PAINT",
            name: "Paint",
            machines: [
              {
                resource_code: "PNT-01",
                name: "Paint line",
                kind: "machine",
                parallel_units: 1,
                has_station_login: true,
              },
            ],
          },
        ],
        operations: [
          {
            resource_code: "PNT-01",
            operation: "Paint",
            erp_min_per_unit: 10.9,
            measured_min_per_unit: FIG(12.9, "min_per_unit", "task_time_median_v1"),
            alternatives: [],
            used_by: ["Frames"],
          },
        ],
        products: [
          {
            sku: "F-200",
            name: "Frame",
            family: "Frames",
            setup_family: "RAL7016",
            sales_price_eur_cents: 98000,
            truly_variable_cost_eur_cents: 43000,
            throughput_per_unit: FIG(55000, "eur_cents", "throughput_per_unit_v1"),
          },
        ],
        changeovers: [
          {
            resource_code: "PNT-01",
            from_setup_family: "RAL7016",
            to_setup_family: "RAL9005",
            changeover_min: 45,
          },
        ],
        capacity_costs: [
          { resource_code: "PNT-01", overtime_eur_cents_per_h: 6250, extra_shift_eur_cents: null },
        ],
        measured_from_import: "i1",
      },
    }),
  );
  await page.route("**/api/plants/PLANT-A/calendar*", (route) =>
    route.fulfill({
      json: {
        plant_code: "PLANT-A",
        timezone_iana: plant.timezone_iana,
        day: "2026-10-13",
        machines: [
          {
            resource_code: "PNT-01",
            name: "Paint line",
            windows: [
              {
                id: 1,
                resource_code: "PNT-01",
                kind: "shift",
                start_at: "2026-10-13T04:00:00Z",
                end_at: "2026-10-13T12:00:00Z",
                covered: false,
                start_min: 360,
                end_min: 840,
              },
              {
                id: 2,
                resource_code: "PNT-01",
                kind: "break",
                start_at: "2026-10-13T09:30:00Z",
                end_at: "2026-10-13T10:00:00Z",
                covered: false,
                start_min: 690,
                end_min: 720,
              },
            ],
          },
        ],
        exceptions: [
          {
            id: 3,
            resource_code: "PNT-01",
            kind: "maintenance",
            start_at: "2026-10-31T05:00:00Z",
            end_at: "2026-10-31T09:00:00Z",
            covered: false,
            start_min: 0,
            end_min: 0,
          },
        ],
        data_start_at: "2026-07-20T04:00:00Z",
        data_end_at: "2026-10-31T09:00:00Z",
        overtime: [{ resource_code: "PNT-01", iso_year: 2026, iso_week: 42, overtime_h: 6.5 }],
      },
    }),
  );
}
