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
const column = (over: Record<string, unknown>) => ({
  table: "Scans.csv",
  fields: [],
  part: null,
  sure: "sure",
  source: "rules",
  reasons: [],
  ai_reason: null,
  personal: false,
  skipped: false,
  question: false,
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
    column({ column: "Tijdstip", fields: ["events.at"] }),
    column({ column: "Xq7", fields: ["events.resource_code"], sure: "likely", question: true }),
    column({
      column: "Kolom 7",
      fields: ["events.quantity_units"],
      sure: "likely",
      source: "ai",
      ai_reason: "Small whole numbers next to the finish events.",
      question: true,
    }),
    column({ column: "Medewerker", personal: true }),
    column({ column: "Datum", fields: ["events.at"], part: "date", table: "Plan.csv" }),
  ],
  fields: {
    events: ["events.resource_code", "events.at", "events.quantity_units", "events.event_type"],
    steps: ["resources.resource_code"],
    calendar: ["calendar.start_at", "calendar.end_at"],
  },
  column_questions: 2,
  ai: { state: "connected" },
  confirmed: null,
};

test.beforeEach(async ({ page }) => {
  await stubApi(page, { role: "it" });
});

test("only the unclear columns are asked, then one summary is confirmed", async ({ page }) => {
  await stubPages(page, { latestImport: { status: "uploaded", recognised: RECOGNISED } });
  const sent: unknown[] = [];
  await page.route("**/api/imports/i1/columns", async (route) => {
    sent.push(route.request().postDataJSON());
    await route.fulfill({ json: {} });
  });
  await page.goto("/import");
  await page.getByRole("tab", { name: /Map columns/ }).click();
  const panel = page.getByRole("region", { name: "What the columns hold" });
  await expect(panel.getByRole("status")).toContainText("We need your answer on 2 columns.");
  await expect(panel).toContainText("Is “Xq7” in Scans.csv the Events (touchpoints) · step code?");
  await expect(panel).toContainText("We think so from its values; its name does not say.");
  // The AI's suggestion is marked and stays a question.
  await expect(panel).toContainText("Suggested by AI");
  await expect(panel).toContainText("Small whole numbers next to the finish events.");
  await panel.getByRole("button", { name: "Yes, Xq7 is that" }).click();
  await expect
    .poll(() => sent)
    .toEqual([{ table: "Scans.csv", column: "Xq7", field: "events.resource_code" }]);
  await panel.getByRole("button", { name: "No, choose what Kolom 7 is" }).click();
  await panel
    .getByRole("combobox", { name: "What is in “Kolom 7” of Scans.csv?" })
    .selectOption({ label: "Not needed: skip this column" });
  await expect.poll(() => sent.length).toBe(2);
  // Summary: personal never read, date half explained; confirm waits for the answers.
  await expect(panel.getByRole("row").filter({ hasText: "Medewerker" })).toContainText(
    "Personal: not read, never stored or shown",
  );
  await expect(panel.getByRole("row").filter({ hasText: "Datum" })).toContainText(
    "The date part; the time comes from another column.",
  );
  await expect(panel.getByRole("button", { name: "Confirm this summary" })).toBeDisabled();
  await expect(panel).toContainText("Answer the 2 questions above first.");
  const axe = await new AxeBuilder({ page }).include("main").analyze();
  expect(axe.violations).toEqual([]);
});

test("without the AI the page says so and how to connect it", async ({ page }) => {
  await stubPages(page, {
    latestImport: {
      status: "uploaded",
      recognised: {
        ...RECOGNISED,
        columns: RECOGNISED.columns.map((c) => ({
          ...c,
          question: false,
          sure: "sure",
          source: "rules",
        })),
        column_questions: 0,
        ai: { state: "not_connected" },
      },
    },
  });
  let confirmed = false;
  await page.route("**/api/imports/i1/mapping/confirm", async (route) => {
    confirmed = true;
    await route.fulfill({ json: {} });
  });
  await page.goto("/import");
  await page.getByRole("tab", { name: /Map columns/ }).click();
  const panel = page.getByRole("region", { name: "What the columns hold" });
  await expect(panel.getByRole("note")).toContainText("AI not connected.");
  await expect(panel.getByRole("note")).toContainText("connect the AI");
  await panel.getByRole("button", { name: "Confirm this summary" }).click();
  await expect.poll(() => confirmed).toBe(true);
});

test("the director sees the summary and who confirmed it, without changing it", async ({
  page,
}) => {
  await stubApi(page, { role: "plant_director" });
  await stubPages(page, {
    latestImport: {
      status: "uploaded",
      recognised: {
        ...RECOGNISED,
        ai: { state: "not_connected" },
        confirmed: { by: "user:1", by_role: "it", at: "2026-10-26T09:30:00+00:00" },
      },
    },
  });
  await page.goto("/import");
  await page.getByRole("tab", { name: /Map columns/ }).click();
  const panel = page.getByRole("region", { name: "What the columns hold" });
  await expect(panel.getByRole("combobox")).toHaveCount(0);
  await expect(panel).toContainText("Confirmed by IT / ERP owner");
  await expect(panel.getByRole("note")).toContainText("Ask IT to connect it.");
});
