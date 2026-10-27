import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { stubApi, stubPages } from "./api";

const table = (name: string, role: string) => ({
  table: name,
  file: name,
  sheet: null,
  role,
  sure: "sure",
  skipped: false,
  reasons: [],
  rows: 10,
  columns: 4,
  personal_columns: 0,
  title_lines: 0,
  totals_lines: 0,
  problem: null,
});
const column = (table: string, column: string, fields: string[]) => ({
  table,
  column,
  fields,
  part: null,
  sure: "sure",
  source: "rules",
  reasons: [],
  ai_reason: null,
  personal: false,
  skipped: false,
  question: false,
});
const code = (over: Record<string, unknown>) => ({
  target: "events.event_type",
  table: "Scans.csv",
  column: "Status",
  meaning: "start",
  sure: "sure",
  source: "rules",
  reasons: ["known_word"],
  ai_reason: null,
  rows: 120,
  skipped: false,
  question: false,
  ...over,
});
const time = (table: string, column: string, over: Record<string, unknown>) => ({
  table,
  column,
  part: null,
  format: "%d-%m-%Y %H:%M",
  options: ["%d-%m-%Y %H:%M"],
  sure: "sure",
  example: "20-07-2026 10:11",
  example_read: "2026-07-20T10:11",
  real_dates: false,
  ...over,
});

const RECOGNISED = {
  tables: [
    table("Scans.csv", "events"),
    table("Steps.csv", "steps"),
    table("Plan.csv", "calendar"),
  ],
  links: [],
  minimum: [
    { key: "events", tables: ["Scans.csv"] },
    { key: "steps", tables: ["Steps.csv"] },
    { key: "calendar", tables: ["Plan.csv"] },
  ],
  not_read: [],
  to_answer: [],
  columns: [
    column("Scans.csv", "Status", ["events.event_type"]),
    column("Scans.csv", "Tijdstip", ["events.at"]),
    column("Steps.csv", "Code", ["resources.resource_code"]),
    column("Plan.csv", "Start", ["calendar.start_at"]),
  ],
  fields: { events: ["events.event_type", "events.at"] },
  column_questions: 0,
  ai: { state: "not_connected" },
  confirmed: null,
  codes: [
    code({ code: "GESTART" }),
    code({
      code: "ANK",
      meaning: "scan",
      sure: "likely",
      reasons: ["shortened_word"],
      rows: 2108,
      question: true,
    }),
  ],
  meanings: {
    "events.event_type": [
      "start",
      "end",
      "setup_start",
      "setup_end",
      "down_start",
      "down_end",
      "scrap",
      "scan",
      "move",
    ],
  },
  code_questions: 1,
  steps: [
    { code: "SNIJ1", name: "Laser cutting", station: "Cutting", kind: null, changed: false },
    { code: "LAK1", name: "Paint line", station: "Paint", kind: "machine", changed: false },
  ],
  formats: {
    times: [
      time("Scans.csv", "Tijdstip", {
        format: null,
        options: ["%d-%m-%Y %H:%M", "%m-%d-%Y %H:%M"],
        sure: null,
        example: "01-08-2026 06:00",
        example_read: null,
      }),
      time("Plan.csv", "Start", {}),
    ],
    date_order: null,
    date_order_question: true,
    date_example: "01-08-2026 06:00",
    date_readings: { day: "2026-08-01T06:00", month: "2026-01-08T06:00" },
    decimal: ",",
    decimal_question: false,
    delimiter: ";",
    title_lines: 0,
    totals_line: false,
    byte_order_mark: false,
    units: [
      {
        table: "Steps.csv",
        column: "Insteltijd",
        target: "routings.standard_setup_min",
        unit: "min",
        field_unit: "min",
        sure: "likely",
      },
    ],
    yes_words: [],
    no_words: ["nee"],
    timezone: "Europe/Amsterdam",
  },
  format_questions: 1,
};

test("an unclear code and the date order are asked; the summary shows codes, steps and dates", async ({
  page,
}) => {
  await stubApi(page, { role: "it" });
  await stubPages(page, { latestImport: { status: "uploaded", recognised: RECOGNISED } });
  const sent: Record<string, unknown[]> = { codes: [], formats: [], steps: [] };
  for (const what of ["codes", "formats", "steps"]) {
    await page.route(`**/api/imports/i1/${what}`, async (route) => {
      sent[what]?.push(route.request().postDataJSON());
      await route.fulfill({ json: {} });
    });
  }
  await page.goto("/import");
  await page.getByRole("tab", { name: /Map columns/ }).click();
  const panel = page.getByRole("region", { name: "What the columns hold" });
  await expect(panel).toContainText(
    "2 codes or formats are unclear. Until you answer, the rows that use them are not imported.",
  );
  await expect(panel).toContainText(
    "Does “ANK” in Status (Scans.csv) mean “Arrived at the step (scan)”?",
  );
  await expect(panel).toContainText("it looks like a shortened word");
  await panel.getByRole("button", { name: "Yes, ANK means that" }).click();
  await expect
    .poll(() => sent.codes)
    .toEqual([{ target: "events.event_type", code: "ANK", meaning: "scan" }]);
  // The date order is asked once, with both readings in plain words.
  await expect(panel).toContainText(
    "Is “01-08-2026 06:00” August 1, 2026 at 06:00 or January 8, 2026 at 06:00?",
  );
  await panel.getByRole("button", { name: /^August 1, 2026/ }).click();
  await expect.poll(() => sent.formats).toEqual([{ date_order: "day" }]);
  // Summary: codes with their meaning and rows, steps with their own codes, dates read.
  const codes = panel.getByRole("table", {
    name: "Codes in Status of Scans.csv and what each means",
  });
  await expect(codes.getByRole("row").filter({ hasText: "GESTART" })).toContainText(
    "Sure: a known word",
  );
  const steps = panel.getByRole("table", { name: "Steps in the steps list" });
  await expect(steps.getByRole("row").filter({ hasText: "SNIJ1" })).toContainText("Cutting");
  await steps
    .getByRole("combobox", { name: "Is step SNIJ1 a machine or handmade?" })
    .selectOption({ label: "Machine" });
  await expect.poll(() => sent.steps).toEqual([{ code: "SNIJ1", kind: "machine" }]);
  const dates = panel.getByRole("table", { name: /Date and time columns/ });
  await expect(dates.getByRole("row").filter({ hasText: "Plan.csv" })).toContainText(
    "July 20, 2026 at 10:11",
  );
  await expect(panel).toContainText("Times are read as Amsterdam time (Plant setup)");
  await expect(panel).toContainText("Decimal mark: comma");
  await expect(panel).toContainText("Yes/no column: “nee” means no.");
  await expect(panel).toContainText("Assumed: the name does not say; please check");
  await expect(panel.getByRole("button", { name: "Confirm this summary" })).toBeDisabled();
  await expect(panel).toContainText("Answer the 2 questions about codes and formats above first.");
  const axe = await new AxeBuilder({ page }).include("main").analyze();
  expect(axe.violations).toEqual([]);
});

test("the director sees what the codes mean without changing them", async ({ page }) => {
  await stubApi(page, { role: "plant_director" });
  await stubPages(page, { latestImport: { status: "uploaded", recognised: RECOGNISED } });
  await page.goto("/import");
  await page.getByRole("tab", { name: /Map columns/ }).click();
  const panel = page.getByRole("region", { name: "What the columns hold" });
  await expect(panel.getByRole("combobox")).toHaveCount(0);
  await expect(panel.getByRole("textbox")).toHaveCount(0);
  const codes = panel.getByRole("table", {
    name: "Codes in Status of Scans.csv and what each means",
  });
  await expect(codes.getByRole("row").filter({ hasText: "GESTART" })).toContainText("Work started");
  await expect(panel.getByRole("button", { name: /^August 1, 2026/ })).toHaveCount(0);
  await expect(panel).toContainText("IT or the planner confirms this summary.");
});
