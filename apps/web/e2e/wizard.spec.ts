import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { stubApi, stubPages } from "./api";

const table = (over: Record<string, unknown>) => ({
  file: "x.csv",
  sheet: null,
  sure: "sure",
  skipped: false,
  reasons: [],
  rows: 10,
  columns: 5,
  personal_columns: 0,
  title_lines: 0,
  totals_lines: 0,
  problem: null,
  ...over,
});

const RECOGNISED = {
  tables: [
    table({ table: "Customers.csv", file: "Customers.csv", role: null, sure: null }),
    table({
      table: "Resources.csv",
      file: "Resources.csv",
      role: "steps",
      sure: "likely",
      rows: 6,
    }),
    table({ table: "Roster.csv", file: "Roster.csv", role: "calendar", rows: 2390 }),
    table({
      table: "ShopFloorEvents.csv",
      file: "ShopFloorEvents.csv",
      role: "events",
      rows: 7084,
      personal_columns: 1,
      title_lines: 2,
      totals_lines: 1,
    }),
  ],
  links: [
    {
      table: "ShopFloorEvents.csv",
      column: "Resource",
      to_table: "Resources.csv",
      to_column: "Resource",
      found: 6,
      total: 6,
      is_list: false,
    },
  ],
  minimum: [
    { key: "events", tables: ["ShopFloorEvents.csv"] },
    { key: "steps", tables: ["Resources.csv"] },
    { key: "calendar", tables: ["Roster.csv"] },
  ],
  not_read: [{ name: "read me.pdf", problem: "not_a_table_file" }],
  to_answer: ["Customers.csv"],
};

test.beforeEach(async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubPages(page, { latestImport: { status: "uploaded", recognised: RECOGNISED } });
});

test("after one upload the page says what each file is and how sure", async ({ page }) => {
  await page.goto("/import");
  const found = page.getByRole("region", { name: "What we found" });
  await expect(found).toContainText("4 tables in 4 files");
  const minimum = found.getByRole("region", { name: "Needed to start a diagnostic" });
  await expect(minimum.getByRole("listitem").filter({ hasText: "Event log" })).toContainText(
    "Found in ShopFloorEvents.csv",
  );
  const events = found.getByRole("row").filter({ hasText: "ShopFloorEvents.csv" });
  await expect(events.getByRole("combobox")).toHaveValue("events");
  await expect(events).toContainText("Sure: its content and name agree");
  await expect(events).toContainText("2 title lines above the header: not read as rows.");
  await expect(events).toContainText("A totals line at the end: not read as rows.");
  await expect(events).toContainText("1 personal column not read");
  await expect(found.getByRole("row").filter({ hasText: "Resources.csv" })).toContainText(
    "Likely: from its content; please check",
  );
  await expect(found.getByRole("region", { name: "How the files link" })).toContainText(
    "ShopFloorEvents.csv › Resource uses the codes in Resources.csv › Resource (6 of 6 found)",
  );
  await expect(found.getByRole("region", { name: "Not read" })).toContainText(
    "read me.pdf: not a table (CSV, TXT or Excel), so it was not stored",
  );
  // The built-in format does not read this event log, so nothing runs before the columns match.
  await expect(page.getByRole("button", { name: /^Run import/ })).toBeDisabled();
  await expect(
    page.getByText(
      "We know what each file is. Next: answer the questions and confirm the summary in step 2 (Map columns).",
    ),
  ).toBeVisible();
  const axe = await new AxeBuilder({ page }).include("main").analyze();
  expect(axe.violations).toEqual([]);
});

test("a file the app cannot place is asked about and can be skipped", async ({ page }) => {
  let sent: unknown = null;
  await page.route("**/api/imports/i1/tables", async (route) => {
    sent = route.request().postDataJSON();
    await route.fulfill({ json: {} });
  });
  await page.goto("/import");
  const found = page.getByRole("region", { name: "What we found" });
  await expect(found.getByRole("status")).toContainText(
    "We could not tell what one file is. Choose what it holds, or skip it.",
  );
  const customers = found.getByRole("combobox", { name: "What is in Customers.csv?" });
  await expect(customers).toHaveValue("");
  await customers.selectOption({ label: "Skip this file: not needed" });
  await expect.poll(() => sent).toEqual({ table: "Customers.csv", role: "skip" });
});

test("the director sees what was found without changing it", async ({ page }) => {
  await stubApi(page, { role: "plant_director" });
  await stubPages(page, { latestImport: { status: "uploaded", recognised: RECOGNISED } });
  await page.goto("/import");
  const found = page.getByRole("region", { name: "What we found" });
  await expect(found.getByRole("combobox")).toHaveCount(0);
  await expect(found.getByRole("row").filter({ hasText: "Roster.csv" })).toContainText(
    "Shift sheet: shifts, breaks and maintenance per step",
  );
});

test("a file with title lines is not marked broken in the file list", async ({ page }) => {
  const file = {
    name: "ShopFloorEvents.csv",
    size_bytes: 1000,
    recognised_as: null,
    feeds: [],
    readable: false,
    problem: "single_column",
    encoding: "utf-8",
    delimiter: ";",
    columns: 1,
    header: ["Report"],
    personal_columns: [],
    rows: 0,
    preview: [],
  };
  await stubPages(page, {
    latestImport: {
      status: "uploaded",
      recognised: RECOGNISED,
      files: [file],
      file_names: [file.name],
    },
  });
  await page.goto("/import");
  const row = page
    .getByRole("region", { name: "Files · standard layout" })
    .getByRole("row")
    .filter({ hasText: "ShopFloorEvents.csv" });
  await expect(row).toContainText("Read: see What we found");
  await expect(row).toContainText("7,084");
  await expect(row).not.toContainText("Only one column");
});
