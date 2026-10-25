import { expect, test } from "@playwright/test";
import { stubApi, stubPages } from "./api";

test("machines show how busy each one is, sorted, and every figure opens its panel", async ({
  page,
}) => {
  await stubApi(page, { role: "planner" });
  await stubPages(page);
  await page.goto("/machines");
  await expect(page.getByText(/is your bottleneck:/)).toContainText("Paint line (PNT-01)");
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

test("the bottleneck is named with its checks, confidence and reasons", async ({ page }) => {
  await stubApi(page, { role: "planner" });
  await stubPages(page);
  await page.goto("/machines");
  const banner = page.getByRole("region", { name: "Your bottleneck" });
  await expect(banner).toContainText("Paint line (PNT-01)");
  await expect(banner).toContainText("4 of 4 checks point at Paint line (PNT-01).");
  await expect(banner).toContainText("high");
  const rows = page.getByRole("table").last().getByRole("row");
  await expect(rows.nth(1).locator("[data-constraint]")).toContainText("PNT-01");

  await banner.getByRole("button", { name: /100%/ }).click();
  await expect(page.getByRole("region", { name: "How this is calculated" })).toContainText(
    "Checks that point at the answer",
  );
  await expect(page.getByRole("region", { name: "How this is calculated" })).toContainText(
    "Busy time check points at",
  );
  await expect(banner).toContainText("Lost at the bottleneck in this period:");
  await expect(banner).toContainText("231 h");
  await expect(banner).toContainText("€433,313");
  await expect(banner).toContainText("Biggest cause: setups");
  await banner.getByRole("button", { name: /€433,313/ }).click();
  const how = page.getByRole("region", { name: "How this is calculated" });
  await expect(how).toContainText("Lost throughput = bottleneck hours lost");
  await expect(how).toContainText("Throughput per bottleneck hour (€): €1,876/h");
  await page.keyboard.press("Escape");
  await banner.getByText("How we found it: 4 checks").click();
  await expect(banner.getByRole("row")).toHaveCount(5);
  await expect(banner).toContainText("The busiest step.");

  await page.getByRole("combobox", { name: "Period" }).selectOption({ label: "July 2026" });
  await expect(banner).toContainText("No step limits your output in this period");
  await expect(banner).toContainText("busy 71% of its available time");
  await expect(page.locator("[data-constraint]")).toHaveCount(0);
});
