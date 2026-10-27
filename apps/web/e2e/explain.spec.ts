import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { stubApi, stubPages } from "./api";

const REJECTED = {
  import_id: "i1",
  total: 3,
  codes: { not_a_datetime: 2, unknown_code: 1 },
  fixed: 0,
  shown: 3,
  offset: 0,
  datetime_format: "20-07-2026 10:11",
  ai: "connected",
  ai_explanations: null,
  rows: [
    {
      file: "mes_events.csv",
      line: 4,
      column: "Tijdstip",
      value: "not a time",
      code: "not_a_datetime",
      reason: "column 'Tijdstip' is not a date and time",
      correction: null,
    },
  ],
};
const EXPLAINED = {
  state: "connected",
  asked_at: "2026-10-26T10:00:00Z",
  items: [
    {
      code: "not_a_datetime",
      explanation: "Some times in Tijdstip are text, not a date and time.",
      fix: "Make the terminal export fill Tijdstip as day-month-year hours:minutes.",
    },
  ],
};

test("without AI each reason says how to fix the export, and why there is no AI advice", async ({
  page,
}) => {
  await stubApi(page, { role: "it" });
  await stubPages(page);
  await page.route("**/api/imports/i1/rejected-rows?*", (route) =>
    route.fulfill({ json: { ...REJECTED, ai: "not_connected" } }),
  );
  await page.goto("/import");
  await page.getByRole("tab", { name: /data checklist/i }).click();
  const help = page.getByRole("region", {
    name: "What went wrong and how to fix it in your export",
  });
  await expect(help).toContainText("Date or time not readable");
  await expect(help).toContainText("It must look like 20-07-2026 10:11.");
  await expect(help).toContainText("Fix in your export: fill in every date and time");
  await expect(help).toContainText("Fix in your export: add the code to the steps list");
  await expect(help).toContainText("AI not connected: these are the standard explanations.");
  await expect(help.getByRole("button", { name: /Ask the AI/ })).toHaveCount(0);
});

test("IT asks the AI for a fix for its own export; it is marked as the AI's", async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubPages(page);
  let asked = 0;
  await page.route("**/api/imports/i1/rejected-rows?*", (route) =>
    route.fulfill({ json: { ...REJECTED, ai_explanations: asked ? EXPLAINED : null } }),
  );
  await page.route("**/api/imports/i1/rejected-rows/explain", (route) => {
    asked += 1;
    return route.fulfill({ json: EXPLAINED });
  });
  await page.goto("/import");
  await page.getByRole("tab", { name: /data checklist/i }).click();
  const help = page.getByRole("region", {
    name: "What went wrong and how to fix it in your export",
  });
  await expect(help).toContainText("The AI sees only the reasons, the file and column names");
  await help.getByRole("button", { name: "Ask the AI how to fix this in your export" }).click();
  await expect(help).toContainText("Suggested by AI for your export: please check");
  await expect(help).toContainText(
    "How to fix it: Make the terminal export fill Tijdstip as day-month-year hours:minutes.",
  );
  await expect(help.getByRole("button", { name: "Ask the AI again" })).toBeVisible();
  expect(asked).toBe(1);
  const axe = await new AxeBuilder({ page }).include("main").analyze();
  expect(axe.violations).toEqual([]);
});

test("the director reads the explanations but cannot ask the AI", async ({ page }) => {
  await stubApi(page, { role: "plant_director" });
  await stubPages(page);
  await page.route("**/api/imports/i1/rejected-rows?*", (route) =>
    route.fulfill({ json: REJECTED }),
  );
  await page.goto("/import");
  await page.getByRole("tab", { name: /data checklist/i }).click();
  const help = page.getByRole("region", {
    name: "What went wrong and how to fix it in your export",
  });
  await expect(help).toContainText("IT or the planner can ask the AI");
  await expect(help.getByRole("button", { name: /Ask the AI/ })).toHaveCount(0);
});

test("Data quality explains each reason next to the rejected rows", async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubPages(page);
  await page.goto("/data");
  const help = page.getByRole("region", {
    name: "What went wrong and how to fix it in your export",
  });
  await expect(help).toContainText("Fix in your export");
  await expect(help.getByRole("link", { name: "Go to Import" })).toHaveAttribute("href", "/import");
});
