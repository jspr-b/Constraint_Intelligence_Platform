import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { stubApi, stubPages } from "./api";

test("results report: answer, cost, the four checks, the data and every source", async ({
  page,
}) => {
  await stubApi(page, { role: "plant_director" });
  await stubPages(page);
  await page.goto("/report");
  const report = page.getByRole("article", { name: "Results report" });
  await expect(report).toContainText("Plant A (synthetic) · PLANT-A");

  const answer = report.getByRole("region", { name: "What limits your output" });
  await expect(answer).toContainText("Paint line (PNT-01) limits your output.");
  await expect(answer).toContainText("It cost you about");

  const cost = report.getByRole("region", { name: "What it cost over the whole data period" });
  await expect(cost).toContainText("In total the bottleneck lost");
  await expect(cost).toContainText("Setups:");

  const sure = report.getByRole("region", { name: "How sure we are: the four checks" });
  await expect(sure).toContainText("because 4 of 4 independent checks point at it.");
  await expect(sure).toContainText("Busy time: points at Paint line (PNT-01)");

  const data = report.getByRole("region", { name: "The data we used, and what was missing" });
  await expect(data).toContainText("events.csv:");
  await expect(data).toContainText("Gap: No breakdowns recorded for PCK-01. Effect on confidence");

  // Every number opens how it is calculated, and points at its numbered source.
  await answer.getByRole("button", { name: /How is Lost throughput calculated/ }).click();
  await expect(page.getByRole("region", { name: "How this is calculated" })).toBeVisible();
  const sources = report.getByRole("region", { name: "Where every number comes from" });
  await expect(sources.locator("#source-1")).toContainText("[1] Lost throughput:");
  await expect(sources.locator("#source-1")).toContainText("Data period:");
  await expect(
    page.getByRole("link", { name: "Back to the short answer on Overview" }),
  ).toBeVisible();
});

test("results report downloads as a PDF named after the plant and period", async ({ page }) => {
  await stubApi(page, { role: "plant_director" });
  await stubPages(page);
  await page.goto("/report");
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Download PDF" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(
    /^results-report_PLANT-A_\d{4}-\d{2}-\d{2}_to_\d{4}-\d{2}-\d{2}\.pdf$/,
  );
  const bytes = readFileSync(await download.path());
  expect(bytes.subarray(0, 5).toString()).toBe("%PDF-");
  await expect(page.getByText(/^Saved to your downloads as results-report_PLANT-A_/)).toBeVisible();
});
