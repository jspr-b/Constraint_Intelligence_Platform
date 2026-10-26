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
  // Every page asks where the numbers are; nothing to say unless a test stubs it.
  await page.route("**/api/refresh-status", (route) => route.fulfill({ json: [] }));
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

const BLOCKED_MISSING = {
  missing: "blocked time",
  reason: "no move/scan events: blocked time cannot be told apart from starved",
  confidence_impact: "medium",
};

const RUN_READY = {
  status: "ready",
  started_at: "2026-10-13T07:16:00Z",
  finished_at: "2026-10-13T07:17:00Z",
  period_start_at: "2026-07-20T04:00:00Z",
  period_end_at: "2026-10-09T20:00:00Z",
  error: null,
};

/** Stored detections: PNT-01 for the whole period and August; no machine binding in July. */
export function stubDetections(kind: string, start: string | null): Record<string, unknown>[] {
  const all =
    kind === "all"
      ? [stubDetection("all", "2026-07-20T04:00:00Z", false)]
      : kind === "month"
        ? [
            stubDetection("month", "2026-07-01T00:00:00Z", true),
            stubDetection("month", "2026-08-01T00:00:00Z", false),
          ]
        : [stubDetection("week", "2026-08-03T00:00:00Z", false)];
  return all.filter((d) => !start || d.period_start_at === start);
}

export function stubDetection(
  kind: string,
  start = "2026-07-20T04:00:00Z",
  market = kind !== "all",
): Record<string, unknown> {
  const method = (m: string, code: string | null, value: number, unit: string, id: string) => ({
    method: m,
    resource_code: market ? null : code,
    top_code: "PNT-01",
    evidence: FIG(value, unit, id),
  });
  return {
    period_kind: kind,
    period_start_at: start,
    period_end_at: "2026-10-09T20:00:00Z",
    resource_code: market ? null : "PNT-01",
    kind: market ? "market" : "internal",
    confidence: market ? "medium" : "high",
    agreement: {
      ...FIG(market ? 0 : 100, "pct", "constraint_agreement_pct_v1"),
      inputs: { utilisation: "PNT-01", queue: "PNT-01", answer: "PNT-01" },
    },
    reasons: market
      ? [{ code: "no_machine_binding", values: { top: "PNT-01", busy_pct: 71.2 } }]
      : [{ code: "methods_agree", values: { count: 4, total: 4, machine: "PNT-01" } }],
    methods: [
      method("utilisation", "PNT-01", 99.9, "pct", "constraint_by_utilisation_v1"),
      method("queue", "PNT-01", 5.2, "orders", "constraint_by_queue_v1"),
      method("active_period", "PNT-01", 96.1, "pct", "constraint_by_active_period_v1"),
      method("starved_blocked", "PNT-01", 0.4, "pct", "constraint_by_starved_blocked_v1"),
    ],
  };
}

/** Measured facts for two machines (Machines page), filtered like the API does. */
export function stubFacts(url: URL): Record<string, unknown>[] {
  const families = url.searchParams.getAll("family");
  const kind = url.searchParams.get("period_kind") ?? "all";
  const only = url.searchParams.get("resource_code");
  const fact = (
    family: string,
    code: string,
    measure: string,
    value: number | typeof BLOCKED_MISSING,
    unit: string,
    formula: string,
    extra: Record<string, unknown> = {},
  ) => ({
    family,
    resource_code: code,
    measure,
    operation: null,
    reason_code: null,
    period_kind: kind,
    figure: {
      ...FIG(0, unit, formula),
      value,
      confidence: typeof value === "number" ? "high" : "none",
      period_start_at: "2026-07-20T04:00:00Z",
      period_end_at: "2026-10-09T20:00:00Z",
    },
    ...extra,
  });
  const out: Record<string, unknown>[] = [];
  const machines: [string, number, number | typeof BLOCKED_MISSING][] = [
    ["PNT-01", 99.88, 0],
    ["WLD-02", 26.37, BLOCKED_MISSING],
  ];
  for (const [code, busy, blocked] of machines) {
    if (only && only !== code) continue;
    if (kind === "day") {
      for (const day of ["2026-07-20", "2026-07-21"]) {
        for (const [state, minutes] of [
          ["shift", 960],
          ["running", 700],
          ["setup", 100],
          ["down", 20],
          ["starved", 40],
          ["break", 100],
        ] as const) {
          const f = fact("state", code, `${state}_min`, minutes, "min", "machine_state_min_v1");
          f.figure.period_start_at = `${day}T04:00:00Z`;
          out.push(f);
        }
      }
      continue;
    }
    const all: Record<string, unknown>[] = [
      fact("utilisation", code, "utilisation_pct", busy, "pct", "utilisation_pct_v1"),
      fact("state_share", code, "running_pct", busy - 12, "pct", "state_share_pct_v1"),
      fact("state_share", code, "setup_pct", 10.7, "pct", "state_share_pct_v1"),
      fact("state_share", code, "down_pct", 1.4, "pct", "state_share_pct_v1"),
      fact("state_share", code, "starved_pct", 0.1, "pct", "state_share_pct_v1"),
      fact("state_share", code, "blocked_pct", blocked, "pct", "state_share_pct_v1"),
      fact("state_share", code, "break_pct", 9.4, "pct", "state_share_pct_v1"),
      fact("state_share", code, "maintenance_pct", 1.9, "pct", "state_share_pct_v1"),
      fact("state_share", code, "unknown_pct", 0, "pct", "state_share_pct_v1"),
      fact("oee", code, "oee_ratio", 0.7253, "ratio", "oee_v1"),
      fact(
        "effective_capacity",
        code,
        "effective_capacity_h",
        838.5,
        "h",
        "effective_capacity_h_v1",
      ),
      fact("state", code, "setup_min", 6164, "min", "machine_state_min_v1"),
      fact("setup_share", code, "setup_share_pct", 12.27, "pct", "setup_share_pct_v1"),
      fact("task_time", code, "median_min_per_unit", 9.41, "min_per_unit", "task_time_median_v1", {
        operation: "Paint",
      }),
      fact("task_time", code, "p90_min_per_unit", 17.47, "min_per_unit", "task_time_p90_v1", {
        operation: "Paint",
      }),
      fact("down_reason", code, "down_min", 359, "min", "down_reason_min_v1", {
        reason_code: "MECH",
      }),
    ];
    const lossStart =
      kind === "all" ? null : kind === "month" ? "2026-08-01T00:00:00Z" : "2026-08-03T00:00:00Z";
    const wanted = url.searchParams.get("period_start_at");
    if (code === "PNT-01" && kind !== "day" && (!wanted || !lossStart || wanted === lossStart)) {
      const rate = FIG(187_581.28, "eur_cents_per_h", "throughput_per_constraint_h_v1");
      for (const [cause, h] of [
        ["setup", 102.8],
        ["breaks", 90],
        ["total", 231],
      ] as const) {
        const hours = FIG(h, "h", "lost_constraint_h_total_v1");
        const lost = fact("loss", code, "lost_h", h, "h", "lost_constraint_h_v1", {
          reason_code: cause,
        });
        all.push({ ...lost, figure: { ...hours, period_start_at: lossStart } });
        all.push({
          ...fact("loss", code, "lost_eur_cents", 0, "eur_cents", "lost_throughput_eur_cents_v1", {
            reason_code: cause,
          }),
          figure: {
            ...FIG(Math.round(h * 187_581.28), "eur_cents", "lost_throughput_eur_cents_v1"),
            inputs: { lost_h: hours, throughput_per_constraint_h_eur_cents: rate },
            period_start_at: lossStart,
          },
        });
      }
    }
    out.push(...all.filter((f) => families.length === 0 || families.includes(f.family as string)));
  }
  return out;
}

/** Synthetic page data for the built foundation pages (accessibility checks see full tables). */
export async function stubPages(
  page: Page,
  overrides: { latestImport?: Record<string, unknown>; factsStatus?: string } = {},
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
  await page.route(/\/api\/plants\/PLANT-A\/facts\/periods$/, (route) =>
    route.fulfill({
      json: [
        {
          period_kind: "all",
          period_start_at: "2026-07-20T04:00:00Z",
          period_end_at: "2026-10-09T20:00:00Z",
        },
        {
          period_kind: "month",
          period_start_at: "2026-07-01T00:00:00Z",
          period_end_at: "2026-08-01T00:00:00Z",
        },
        {
          period_kind: "month",
          period_start_at: "2026-08-01T00:00:00Z",
          period_end_at: "2026-09-01T00:00:00Z",
        },
      ],
    }),
  );
  await page.route(/\/api\/plants\/PLANT-A\/facts(\?.*)?$/, (route) =>
    route.fulfill({
      json: {
        plant_code: "PLANT-A",
        run: {
          status: overrides.factsStatus ?? "ready",
          started_at: "2026-10-13T07:16:00Z",
          // The first calculation: no earlier numbers to keep showing.
          finished_at:
            (overrides.factsStatus ?? "ready") === "ready" ? "2026-10-13T07:17:00Z" : null,
          period_start_at: "2026-07-20T04:00:00Z",
          period_end_at: "2026-10-09T20:00:00Z",
          error: null,
        },
        import_id: "i1",
        facts:
          overrides.factsStatus && overrides.factsStatus !== "ready"
            ? []
            : stubFacts(new URL(route.request().url())),
      },
    }),
  );
  await page.route(/\/api\/plants\/PLANT-A\/detection(\?.*)?$/, (route) => {
    const params = new URL(route.request().url()).searchParams;
    const kind = params.get("period_kind") ?? "all";
    const status = overrides.factsStatus ?? "ready";
    route.fulfill({
      json: {
        plant_code: "PLANT-A",
        run: {
          ...RUN_READY,
          status,
          finished_at: status === "ready" ? RUN_READY.finished_at : null,
        },
        import_id: "i1",
        detections: status !== "ready" ? [] : stubDetections(kind, params.get("period_start_at")),
      },
    });
  });
  await page.route("**/api/onboarding*", (route) =>
    route.fulfill({
      json: {
        plant_code: "PLANT-A",
        plant_name: "Plant A (synthetic)",
        steps: ["plant", "upload", "check", "answer"].map((key) => ({
          key,
          state: "done",
          detail: null,
          missing: [],
        })),
        next_step: null,
        complete: true,
        can_set_up: true,
        setup_contacts: [],
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
          file_names: ["mes_events.csv", "notes.csv"],
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
          facts: {
            status: "ready",
            started_at: "2026-10-13T07:16:00Z",
            finished_at: "2026-10-13T07:17:00Z",
            period_start_at: "2026-07-20T04:00:00Z",
            period_end_at: "2026-10-10T14:00:00Z",
            error: null,
          },
          ...overrides.latestImport,
        },
      ],
    }),
  );
  await page.route("**/api/plants/PLANT-A/data-quality", (route) =>
    route.fulfill({
      json: {
        plant_code: "PLANT-A",
        import_id: "i1",
        imported_at: "2026-10-13T07:15:00Z",
        score: FIG(94, "score", "data_quality_score_v1"),
        rows: FIG(11684, "rows", "record_count_v1"),
        files: [
          {
            file: "events.csv",
            rows: 7084,
            rejected: 2,
            fixed: 0,
            reasons: { bad_time: 2 },
            examples: [],
          },
        ],
        files_required: 8,
        files_missing: [],
        gaps: [
          {
            code: "no_breakdowns",
            description: "No breakdowns recorded for PCK-01",
            confidence_impact: "low",
            fix: "Confirm the step had no stops, or add the maintenance log",
            resource_code: "PCK-01",
            count: 1,
          },
        ],
        event_period_weeks: FIG(11.7, "weeks", "event_period_weeks_v1"),
        event_period_start_at: "2026-07-20T04:00:00Z",
        event_period_end_at: "2026-10-09T16:00:00Z",
      },
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
