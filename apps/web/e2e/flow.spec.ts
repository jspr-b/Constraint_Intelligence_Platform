import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { stubApi, stubPages } from "./api";

/** The flow found in the data (CI0005 seq 06): routes with explained shares, on a canvas. */
const period = { period_start_at: "2026-07-20T04:00:00Z", period_end_at: "2026-10-09T20:00:00Z" };
const share = (jobs: number, of: number) => ({
  value: Math.round((1000 * jobs) / of) / 10,
  unit: "pct",
  formula_id: "flow_share_pct_v1",
  inputs: { jobs_this_way: jobs, jobs_counted: of },
  ...period,
  confidence: "high",
});
const arrow = (from: string, to: string, jobs: number, of: number, extra = {}) => ({
  from_step: from,
  to_step: to,
  jobs,
  share: share(jobs, of),
  rework: false,
  uncertain_jobs: 0,
  less_certain: false,
  ...extra,
});
const step = (code: string, jobs: number, first = 0, last = 0, missing = 0) => ({
  code,
  jobs,
  first_jobs: first,
  last_jobs: last,
  missing_finish: missing,
});
const FLOW = {
  plant_code: "PLANT-A",
  run: {
    status: "ready",
    started_at: "2026-10-12T05:00:00Z",
    finished_at: "2026-10-12T05:01:00Z",
    ...period,
    error: null,
  },
  import_id: "i1",
  jobs: 100,
  routes: [
    {
      steps: ["CUT-01", "WLD-01", "PNT-01"],
      jobs: 60,
      share: share(60, 100),
      rework: false,
      uncertain_jobs: 0,
      less_certain: false,
    },
    {
      steps: ["CUT-01", "WLD-02", "PNT-01"],
      jobs: 40,
      share: share(40, 100),
      rework: false,
      uncertain_jobs: 0,
      less_certain: false,
    },
  ],
  other_routes_jobs: 0,
  arrows: [
    arrow("CUT-01", "WLD-01", 60, 100),
    arrow("CUT-01", "WLD-02", 40, 100),
    arrow("WLD-01", "PNT-01", 60, 70),
    arrow("WLD-02", "PNT-01", 40, 40, { uncertain_jobs: 8, less_certain: true }),
    arrow("WLD-01", "CUT-01", 10, 70, { rework: true, less_certain: true }),
  ],
  steps: [
    step("CUT-01", 100, 100),
    step("PNT-01", 100, 0, 98),
    step("WLD-01", 60, 0, 0, 1),
    step("WLD-02", 40, 0, 2),
  ],
  overlapping_jobs: 0,
  ...period,
  rule: "steps of a job in order of their start touchpoints",
};
const RESOURCES = [
  ["CUT-01", "Laser cutting", "CUTTING", "Cutting"],
  ["WLD-01", "Welding 1", "WELD", "Welding cell"],
  ["WLD-02", "Welding 2", "WELD", "Welding cell"],
  ["PNT-01", "Paint line", "PAINT", "Paint"],
].map(([resource_code, name, station_code, station_name]) => ({
  resource_code,
  name,
  kind: "machine",
  station_code,
  station_name,
  parallel_units: 1,
  positions_max: 1,
}));

async function open(page: Page, flow: unknown = FLOW) {
  await stubApi(page, { role: "it" });
  await stubPages(page);
  await page.route("**/api/plants/PLANT-A/resources", (route) =>
    route.fulfill({ json: RESOURCES }),
  );
  await page.route("**/api/plants/PLANT-A/flow", (route) => route.fulfill({ json: flow }));
  await page.goto("/import");
  await page.getByRole("tab", { name: /Flow/ }).click();
}

test("the flow found in the data shows each share and how it was counted", async ({ page }) => {
  await open(page);
  await expect(
    page.getByRole("heading", { name: "This is the flow we found in your data" }),
  ).toBeVisible();
  const canvas = page.getByTestId("flow-canvas");
  await expect(canvas.getByText("Welding cell")).toBeVisible();
  await expect(canvas.getByText("WLD-02")).toBeVisible();
  await canvas.getByRole("button", { name: /^CUT-01 → WLD-01: 60%/ }).click();
  const details = page.getByRole("complementary").filter({ hasText: "Share of jobs" });
  await expect(details).toContainText("Jobs that went this way: 60");
  await expect(details).toContainText("Jobs counted: 100");
  await canvas.getByRole("button", { name: /^WLD-01 → CUT-01: 14.3% rework/ }).click();
  await expect(page.getByRole("complementary").filter({ hasText: "Share of jobs" })).toContainText(
    "rework",
  );
  await canvas.getByRole("button", { name: /^WLD-02 → PNT-01: 100%/ }).click();
  await expect(page.getByRole("complementary").filter({ hasText: "Share of jobs" })).toContainText(
    "Less certain: 8 jobs",
  );
  await expect(canvas.getByRole("button", { name: /^Input → CUT-01: 100 jobs/ })).toBeVisible();
  // Few jobs end at WLD-02: listed under the canvas, not drawn as an arrow.
  await expect(page.getByText(/A few jobs end early/)).toContainText("WLD-02");
});

test("full screen opens the whole working area and Esc closes it", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Full screen" }).click();
  const full = page.getByRole("dialog", { name: "Plant flow, full screen" });
  await expect(full).toBeVisible();
  await expect(full.getByRole("button", { name: "Reorganize" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(full).toHaveCount(0);
});

test("reorganize can be undone", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("button", { name: "Undo" })).toBeDisabled();
  await page.getByRole("button", { name: "Reorganize" }).click();
  await expect(page.getByRole("button", { name: "Undo" })).toBeEnabled();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("button", { name: "Undo" })).toBeDisabled();
});

test("movement is off for viewers who prefer reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page);
  await expect(page.getByRole("button", { name: "Movement" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("before any upload the flow says what to do", async ({ page }) => {
  await open(page, {
    ...FLOW,
    run: null,
    import_id: null,
    jobs: 0,
    routes: [],
    arrows: [],
    steps: [],
  });
  await expect(page.getByText(/No flow yet/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Upload your export" })).toBeVisible();
});

for (const theme of ["white", "dark"]) {
  test(`the flow canvas has no serious axe violations (${theme})`, async ({ page, context }) => {
    await context.addCookies([{ name: "cip_theme", value: theme, url: "http://localhost:3300" }]);
    await open(page);
    await expect(page.getByTestId("flow-canvas").getByText("PNT-01")).toBeVisible();
    const results = await new AxeBuilder({ page })
      .include("[data-testid=flow-canvas]")
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    const blocking = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(
      blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
    ).toEqual([]);
  });
}
