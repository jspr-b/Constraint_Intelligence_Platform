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

const REJECTED = {
  import_id: "i1",
  total: 1,
  codes: { unknown_code: 1 },
  fixed: 0,
  shown: 1,
  offset: 0,
  datetime_format: "20-07-2026 10:11",
  rows: [
    {
      file: "mes_events.csv",
      line: 4,
      column: "Werkplek",
      value: "LAS9",
      code: "unknown_code",
      reason: "unknown code 'LAS9' in column 'Werkplek'",
      correction: null,
    },
  ],
};

test("IT fixes a rejected row with a reason; the file stays as uploaded", async ({ page }) => {
  let sent: Record<string, unknown> | null = null;
  await page.route("**/api/imports/i1/rejected-rows?*", (route) =>
    route.fulfill({ json: REJECTED }),
  );
  await page.route("**/api/imports/i1/corrections", (route) => {
    sent = route.request().postDataJSON() as Record<string, unknown>;
    return route.fulfill({
      status: 422,
      json: {
        code: "correction_still_rejected",
        message:
          "The import still cannot read this value. It needs a code the plant's export uses. Nothing was saved.",
      },
    });
  });
  await page.goto("/import");
  await page.getByRole("tab", { name: /data checklist/i }).click();
  const panel = page.getByRole("region", { name: "Rejected rows" });
  await expect(panel).toContainText("This code is not one the export uses");
  await expect(panel).toContainText("LAS9");
  await panel.getByRole("button", { name: "Fix line 4 of mes_events.csv" }).click();
  const dialog = page.getByRole("dialog", { name: "Fix line 4 of mes_events.csv" });
  await dialog.getByLabel("Right value for Werkplek").fill("LAS1");
  await dialog.getByLabel("Why (required)").fill("typo at the terminal");
  await dialog.getByRole("button", { name: "Save fix" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Nothing was saved");
  expect(sent).toMatchObject({
    file: "mes_events.csv",
    line: 4,
    column: "Werkplek",
    value: "LAS1",
    exclude: false,
    reason: "typo at the terminal",
  });
});

test("Data quality lists the fixes with their reason, a CSV download and undo", async ({
  page,
}) => {
  await page.route("**/api/plants/PLANT-A/corrections", (route) =>
    route.fulfill({
      json: [
        {
          correction_id: "c1",
          plant_code: "PLANT-A",
          action: "set",
          import_id: "i1",
          import_created_at: "2026-10-13T07:15:00Z",
          file: "mes_events.csv",
          line: 4,
          column: "Werkplek",
          original: "LAS9",
          value: "LAS1",
          target: null,
          target_key: null,
          event_at: "2026-09-02T08:00:00Z",
          reason: "typo at the terminal",
          role: "it",
          created_at: "2026-10-14T09:00:00Z",
          undone_at: null,
          undone: false,
        },
      ],
    }),
  );
  await page.goto("/data");
  const fixed = page.getByRole("region", { name: "Fixed in the app" });
  await expect(fixed).toContainText("line 4 of mes_events.csv: Werkplek “LAS9” → “LAS1”");
  await expect(fixed).toContainText("typo at the terminal");
  await expect(fixed.getByRole("link", { name: /Download as CSV/ })).toHaveAttribute(
    "href",
    "/api/plants/PLANT-A/corrections.csv",
  );
  await expect(fixed.getByRole("button", { name: /^Undo: line 4/ })).toBeVisible();
});

test("deleting an import first shows what goes, then deletes it for good", async ({ page }) => {
  let deleted = false;
  await page.route("**/api/imports/i1/delete-preview", (route) =>
    route.fulfill({
      json: {
        in_use: true,
        events_before: 7084,
        events_after: 0,
        events_removed: 7084,
        period_before: ["2026-07-20T04:00:00Z", "2026-10-09T20:00:00Z"],
        period_after: [null, null],
        lists: [{ name: "resources", before: 6, after: 0, new: [], gone: [] }],
        lists_after: [],
        warnings: [],
        corrections: 2,
        falls_back_to: null,
        imports_left: 0,
      },
    }),
  );
  await page.route("**/api/imports/i1", (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    deleted = true;
    return route.fulfill({ status: 204 });
  });
  await page.goto("/import");
  const history = page.getByRole("region", { name: "Import history" });
  await history.getByRole("button", { name: /^Delete the upload of/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("7,084");
  await expect(dialog).toContainText("steps list: no other upload has it, so it goes");
  await expect(dialog).toContainText("2 rows fixed in the app go with it.");
  await expect(dialog).toContainText("No import is left");
  expect(deleted).toBe(false);
  await dialog.getByRole("button", { name: "Delete for good" }).click();
  await expect(dialog).toBeHidden();
  expect(deleted).toBe(true);
});

test("IT deletes all data of a plant only with the plant code typed", async ({ page }) => {
  await page.route("**/api/plants/PLANT-A/data?*", (route) =>
    route.fulfill(
      new URL(route.request().url()).searchParams.get("confirm") === "PLANT-A"
        ? { status: 204 }
        : {
            status: 422,
            json: {
              code: "plant_delete_confirm",
              message: "Type the plant code PLANT-A exactly to confirm. Nothing was deleted.",
            },
          },
    ),
  );
  await page.goto("/import");
  await page.getByText("Delete all data of this plant").click();
  await page.getByRole("button", { name: "Delete all data of PLANT-A" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Type PLANT-A to confirm").fill("PLANT-B");
  await dialog.getByRole("button", { name: "Delete everything" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Nothing was deleted");
  await dialog.getByLabel("Type PLANT-A to confirm").fill("PLANT-A");
  await dialog.getByRole("button", { name: "Delete everything" }).click();
  await expect(dialog).toBeHidden();
});
