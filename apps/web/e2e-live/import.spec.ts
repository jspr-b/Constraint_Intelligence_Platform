import { readdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

const EXPORT = join(process.cwd(), "../../data/synthetic/plant_a/erp_export/clean/csv");

test("IT imports plant_a's ERP export: personal column dropped, checklist filled", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("it@e2e.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/conn$/);

  await page.goto("/import");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("No import for this plant yet.")).toBeVisible();
  const files = readdirSync(EXPORT).map((f) => join(EXPORT, f));
  await page.getByLabel("CSV or Excel exports").setInputFiles(files);
  await page.getByRole("button", { name: "Upload files" }).click();
  await expect(page.getByRole("cell", { name: "mes_events.csv", exact: true })).toBeVisible();

  // Step 1 tells what each file is before anything is imported.
  const eventsRow = page.getByRole("row").filter({ hasText: "mes_events.csv" });
  await expect(eventsRow).toContainText("Operation events (MES)");
  await expect(eventsRow).toContainText("Readable, ready to import");
  await expect(eventsRow).toContainText("1 personal column dropped");
  await page.getByRole("button", { name: "Show first rows of mes_events.csv" }).click();
  const preview = page.getByRole("table", { name: "First rows of mes_events.csv" });
  await expect(preview.getByRole("columnheader", { name: /Medewerker/ })).toContainText(
    "Not imported",
  );
  await expect(preview.getByRole("row")).toHaveCount(6);
  await expect(
    page.getByRole("region", { name: /Needed to start a diagnostic/ }),
  ).not.toContainText("Missing");

  await page.getByRole("tab", { name: /Map columns/ }).click();
  const events = page.getByRole("region", { name: "mes_events.csv" });
  const personal = events.getByRole("row").filter({ hasText: "Medewerker" });
  await expect(personal).toContainText("Not imported");
  await expect(personal).toContainText("Personal data: dropped on import, never stored");

  await page.getByRole("tab", { name: /Upload files/ }).click();
  await page.getByRole("button", { name: "Run import" }).click();
  await expect(page.getByText("DONE")).toBeVisible({ timeout: 90_000 });

  await page.getByRole("tab", { name: /data checklist/i }).click();
  const results = page.getByRole("region", { name: "Results per file" });
  await expect(results.getByRole("row").filter({ hasText: "mes_events.csv" })).toContainText(
    "Imported",
  );
  await expect(results.getByRole("row").filter({ hasText: "mes_events.csv" })).toContainText(
    /events \d/,
  );
  const minimum = page.getByRole("region", { name: /Minimum to start a diagnostic/ });
  for (const item of [
    "Orders",
    "Routings and operations per machine",
    "Operation events (8+ weeks)",
  ]) {
    await expect(minimum.getByRole("listitem").filter({ hasText: item })).toContainText("OK");
  }
  await expect(page.getByRole("region", { name: "Data checklist" })).toBeVisible();
});

test("plant setup shows engine numbers from the import and takes kick-off entries", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("it@e2e.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/conn$/);
  await page.goto("/setup");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText(/6 machines/)).toBeVisible();

  await page.getByRole("tab", { name: "Operations" }).click();
  const measured = page.getByRole("button", { name: /min\/unit/ }).first();
  await measured.focus();
  await expect(page.getByRole("tooltip")).toContainText("task_time_median_v1");

  await page.getByRole("tab", { name: "Products" }).click();
  const throughput = page.getByRole("button", { name: /€/ }).first();
  await throughput.focus();
  await expect(page.getByRole("tooltip")).toContainText("throughput_per_unit_v1");

  await page.getByRole("tab", { name: "Stations and machines" }).click();
  await page.getByRole("button", { name: "Add station" }).click();
  let dialog = page.getByRole("dialog", { name: "Add station" });
  await dialog.getByLabel("Station code").fill("qa");
  await dialog.getByLabel("Station name").fill("Quality check");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: /Quality check/ })).toBeVisible();

  await page.getByRole("button", { name: "Add machine" }).click();
  dialog = page.getByRole("dialog", { name: "Add machine" });
  await dialog.getByLabel("Machine code").fill("qa-01");
  await dialog.getByLabel("Machine name").fill("Inspection bench");
  await dialog.getByLabel("Station").selectOption("QA");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/7 machines/)).toBeVisible();

  await page.getByRole("tab", { name: "Capacity costs" }).click();
  await page.getByRole("button", { name: "Edit costs PNT-01" }).click();
  dialog = page.getByRole("dialog", { name: "Edit costs PNT-01" });
  await dialog.getByLabel("Overtime € /hour").fill("62,50");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("row").filter({ hasText: "PNT-01" })).toContainText("€62.50");
});

test("capacity calendar: timeline, covered break, maintenance and overtime", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("it@e2e.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/conn$/);
  await page.goto("/calendar");
  await page.waitForLoadState("networkidle");
  const paint = page.getByRole("list", { name: "PNT-01" });
  await expect(paint.getByRole("listitem").first()).toBeAttached();

  const lunch = paint.getByRole("button", { name: /^Break: machine stops/ }).first();
  const name = (await lunch.getAttribute("aria-label")) ?? "";
  const time = name.replace(/^Break: machine stops /, "").split(".")[0] ?? "";
  await lunch.click();
  await expect(
    paint.getByRole("button", { name: new RegExp(`^Break covered: keeps running ${time}`) }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Add to calendar" }).click();
  const dialog = page.getByRole("dialog", { name: "Add to calendar" });
  await dialog.getByLabel("Machine").selectOption("PNT-01");
  await dialog.getByLabel("Kind").selectOption("maintenance");
  await dialog.getByLabel("From").fill("18:00");
  await dialog.getByLabel("Until", { exact: true }).fill("22:00");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(
    page
      .getByRole("region", { name: /Exceptions/ })
      .getByRole("row")
      .filter({ hasText: "PNT-01" })
      .filter({ hasText: /18:00/ })
      .filter({ hasText: "Maintenance" }),
  ).toHaveCount(1);

  await page.getByRole("button", { name: "Enter overtime" }).click();
  const overtime = page.getByRole("dialog", { name: "Enter overtime" });
  await overtime.getByLabel("Machine").selectOption("PNT-01");
  await overtime.getByLabel("Week").fill("42");
  await overtime.getByLabel("Hours").fill("6,5");
  await overtime.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("region", { name: /Overtime worked/ })).toContainText("6.5 h");
});

test("connections: IT start page shows the last import and runs it again", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("it@e2e.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/conn$/);
  await page.waitForLoadState("networkidle");
  const sources = page.getByRole("region", { name: "Connections · read-only" });
  await expect(sources).toContainText("WRITE-BACK TO ERP: OFF");
  const upload = sources.getByRole("row").filter({ hasText: "ERP and MES exports" });
  await expect(upload).toContainText("OK");
  await expect(sources.getByRole("row").filter({ hasText: "Machine gateway" })).toContainText(
    "Not connected (later)",
  );
  await expect(page.getByRole("region", { name: "Data protection" })).toContainText(
    "row-level security",
  );
  await page.getByRole("button", { name: "Run import now" }).click();
  await expect(upload).toContainText("Running");
  await expect(upload).toContainText("OK", { timeout: 90_000 });
});
