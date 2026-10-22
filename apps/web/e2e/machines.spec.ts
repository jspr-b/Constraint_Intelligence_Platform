import { expect, test } from "@playwright/test";
import { stubApi, stubPages } from "./api";

test("machines show how busy each one is, sorted, and every figure opens its panel", async ({
  page,
}) => {
  await stubApi(page, { role: "planner" });
  await stubPages(page);
  await page.goto("/machines");
  await expect(page.getByText(/is your busiest machine/)).toContainText("Paint line (PNT-01)");
  const rows = page.getByRole("table").first().getByRole("row");
  await expect(rows.nth(1)).toContainText("PNT-01");
  await expect(rows.nth(1)).toContainText("99.9%");
  await expect(rows.nth(1)).toContainText("72.5%");

  await page.getByRole("button", { name: "Sort by Busy" }).click();
  await expect(rows.nth(1)).toContainText("WLD-02");

  await rows
    .nth(2)
    .getByRole("button", { name: /99\.9%/ })
    .click();
  const panel = page.getByRole("region", { name: "How this is calculated" });
  await expect(panel).toContainText("Busy = (running + setup)");
});

test("machine details show the day timeline, task times, breakdowns and missing data", async ({
  page,
}) => {
  await stubApi(page, { role: "planner" });
  await stubPages(page);
  await page.goto("/machines");
  await page.getByRole("button", { name: "Show details of WLD-02 (WLD-02)" }).click();
  const detail = page.getByRole("region", { name: "WLD-02 (WLD-02) · details" });
  await expect(detail.getByText("Where each day's shift time went")).toBeVisible();
  await detail
    .getByRole("button", { name: /Running$/ })
    .first()
    .click();
  await expect(page.getByRole("region", { name: "How this is calculated" })).toContainText(
    "700 min",
  );
  await expect(detail.getByRole("row").filter({ hasText: "Paint" })).toContainText("9.4 min/unit");
  await expect(detail.getByRole("row").filter({ hasText: "MECH" })).toContainText("359 min");
  await expect(detail.getByText(/blocked time: no move\/scan events/)).toBeVisible();
  await expect(detail.getByText(/not split by reason/)).toBeVisible();
});

test("before the numbers are ready the page says why and where to go", async ({ page }) => {
  await stubApi(page, { role: "planner" });
  await stubPages(page, { factsStatus: "calculating" });
  await page.goto("/machines");
  await expect(page.getByText(/Calculating your numbers from the latest import/)).toBeVisible();
});
