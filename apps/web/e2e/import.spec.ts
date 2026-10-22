import { expect, test } from "@playwright/test";
import { stubApi, stubPages } from "./api";

test.beforeEach(async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubPages(page);
});

test("the import page explains each file before running", async ({ page }) => {
  await page.goto("/import");
  await expect(page.getByText("How importing works")).toBeVisible();
  const events = page.getByRole("row").filter({ hasText: "mes_events.csv" });
  await expect(events).toContainText("Operation events (MES)");
  await expect(events).toContainText("Readable, ready to import");
  const notes = page.getByRole("row").filter({ hasText: "notes.csv" });
  await expect(notes).toContainText("Only one column: the separator may be wrong");
  await expect(page.getByText(/1 file is not recognised and will be ignored/)).toBeVisible();
  const needed = page.getByRole("region", { name: /Needed to start a diagnostic/ });
  await expect(needed.getByRole("listitem").filter({ hasText: "Orders" })).toContainText(
    "Missing: upload orders.csv",
  );
  await page.getByRole("button", { name: "Show first rows of mes_events.csv" }).click();
  const preview = page.getByRole("table", { name: "First rows of mes_events.csv" });
  await expect(preview.getByRole("columnheader", { name: /Medewerker/ })).toContainText(
    "Not imported",
  );
  await expect(preview.getByRole("cell", { name: "LAK1" })).toBeVisible();
});

test("results per file show rejected rows with reason and lines", async ({ page }) => {
  await page.goto("/import");
  await page.getByRole("tab", { name: /data checklist/i }).click();
  const row = page
    .getByRole("region", { name: "Results per file" })
    .getByRole("row")
    .filter({ hasText: "mes_events.csv" });
  await expect(row).toContainText("Imported, some rows rejected");
  await expect(row).toContainText("unknown: 1 (lines 4)");
  await expect(row).toContainText("events 9");
});

test("the import can be run from the Map columns step too", async ({ page }) => {
  await page.goto("/import");
  await page.getByRole("tab", { name: /Map columns/ }).click();
  await expect(page.getByRole("button", { name: "Run import again" })).toBeVisible();
});
