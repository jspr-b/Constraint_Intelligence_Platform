import { expect, test } from "@playwright/test";
import { stubApi, stubPages } from "./api";

test.beforeEach(async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubPages(page);
});

test("the import page explains each file before running", async ({ page }) => {
  await page.goto("/import");
  await expect(page.getByText("How importing works")).toBeVisible();
  const events = page
    .getByRole("region", { name: /Files · standard layout/ })
    .getByRole("row")
    .filter({ hasText: "mes_events.csv" });
  await expect(events).toContainText("Operation events (MES)");
  await expect(events).toContainText("Readable, ready to import");
  const notes = page
    .getByRole("region", { name: /Files · standard layout/ })
    .getByRole("row")
    .filter({ hasText: "notes.csv" });
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
  await expect(row).toContainText("Events (touchpoints) 9");
});

test("the import can be run from the Map columns step too", async ({ page }) => {
  await page.goto("/import");
  await page.getByRole("tab", { name: /Map columns/ }).click();
  await expect(page.getByRole("button", { name: "Run import again" })).toBeVisible();
});

test("after an import the page says when the numbers are calculated", async ({ page }) => {
  await page.goto("/import");
  const ready = page.getByRole("status").filter({ hasText: "Your numbers are calculated for" });
  await expect(ready).toContainText("2026");
  await page.getByRole("link", { name: "Next: check your data" }).click();
  await expect(page).toHaveURL(/\/data$/);
});

test("while the numbers are calculated the page says so and run waits", async ({ page }) => {
  await stubPages(page, {
    latestImport: {
      facts: {
        status: "calculating",
        started_at: "2026-10-13T07:16:00Z",
        finished_at: null,
        period_start_at: null,
        period_end_at: null,
        error: null,
      },
    },
  });
  await page.goto("/import");
  await expect(page.getByText(/Calculating your numbers from this import/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Run import again" })).toHaveCount(0);
});

test("a failed calculation says what to do and keeps the details for IT", async ({ page }) => {
  await stubPages(page, {
    latestImport: {
      facts: {
        status: "failed",
        started_at: "2026-10-13T07:16:00Z",
        finished_at: "2026-10-13T07:17:00Z",
        period_start_at: null,
        period_end_at: null,
        error: "facts:ValueError",
      },
    },
  });
  await page.goto("/import");
  const alert = page.getByRole("alert").filter({ hasText: "could not calculate your numbers" });
  await expect(alert).toContainText("Run the import again");
  await expect(alert.getByText("facts:ValueError")).toBeHidden();
});

test("an upload replaced by a newer version still shows what it did", async ({ page }) => {
  await stubPages(page, { latestImport: { status: "replaced" } });
  await page.goto("/import");
  await expect(page.getByText(/A newer version replaced this upload/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Run import again" })).toHaveCount(0);
  await page.getByRole("tab", { name: /data checklist/i }).click();
  await expect(
    page.getByRole("region", { name: "Results per file" }).getByRole("row").filter({
      hasText: "mes_events.csv",
    }),
  ).toContainText("Imported, some rows rejected");
});
