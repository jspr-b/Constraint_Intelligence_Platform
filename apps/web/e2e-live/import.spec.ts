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
  await page.getByLabel("CSV, TXT or Excel files, or a zip").setInputFiles(files);
  await page.getByRole("button", { name: "Upload files" }).click();
  await expect(
    page
      .getByRole("region", { name: /Files · standard layout/ })
      .getByRole("cell", { name: "mes_events.csv", exact: true }),
  ).toBeVisible();

  // Step 1 tells what each file is before anything is imported.
  const eventsRow = page
    .getByRole("region", { name: /Files · standard layout/ })
    .getByRole("row")
    .filter({ hasText: "mes_events.csv" });
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
  await expect(
    page
      .getByRole("region", { name: /Files · standard layout/ })
      .getByText("IN USE", { exact: true }),
  ).toBeVisible({
    timeout: 90_000,
  });

  await page.getByRole("tab", { name: /data checklist/i }).click();
  const results = page.getByRole("region", { name: "Results per file" });
  await expect(results.getByRole("row").filter({ hasText: "mes_events.csv" })).toContainText(
    "Imported",
  );
  await expect(results.getByRole("row").filter({ hasText: "mes_events.csv" })).toContainText(
    /Events \(touchpoints\) \d/,
  );
  const minimum = page.getByRole("region", { name: /Minimum to start a diagnostic/ });
  for (const item of [
    "Event log: start and finish per job and step",
    "Steps list",
    "Shift sheet",
  ]) {
    await expect(minimum.getByRole("listitem").filter({ hasText: item })).toContainText("OK");
  }
  await expect(page.getByRole("region", { name: "Data checklist" })).toBeVisible();
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
    "Separate from every other company",
  );
  // Running the same export again adds nothing new (ADR-0010), so "Running" may pass too fast to
  // see; the run being accepted and the row back at OK is what the client gets.
  const ran = page.waitForResponse(
    (r) => /\/imports\/[^/]+\/run$/.test(r.url()) && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Run import now" }).click();
  const status = (await ran).status();
  if (status === 409) {
    // The answer of the first import may still be calculating: the page says so; try again.
    await expect(
      page.getByRole("alert").filter({ hasText: "Your change was not saved" }),
    ).toBeVisible();
    await expect(async () => {
      const again = page.waitForResponse((r) => /\/imports\/[^/]+\/run$/.test(r.url()));
      await page.getByRole("button", { name: "Run import now" }).click();
      expect((await again).status()).toBe(202);
    }).toPass({ timeout: 90_000, intervals: [3_000] });
  } else {
    expect(status).toBe(202);
  }
  await expect(upload).toContainText("OK", { timeout: 90_000 });
});
