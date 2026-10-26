import { readdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

const BROKEN = join(process.cwd(), "../../data/synthetic/import_cases/broken/upload_1");

test("IT fixes a rejected row in the app, sees it on Data quality, and undoes it", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("it@e2e.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/conn$/);

  // Its own plant, so the fixes do not change the answers the other specs check (ADR-0010).
  await page.goto("/setup");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Add plant" }).first().click();
  const add = page.getByRole("dialog");
  await add.getByLabel(/Short plant code/).fill("PLANT-F");
  await add.getByLabel("Name").fill("Plant A with typing errors (synthetic)");
  await add.getByRole("button", { name: "Save" }).click();
  await expect(add).toBeHidden();

  await page.goto("/import");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Plant", { exact: true }).selectOption("PLANT-F");
  await page
    .getByLabel("CSV or Excel exports")
    .setInputFiles(readdirSync(BROKEN).map((f) => join(BROKEN, f)));
  await page.getByRole("button", { name: "Upload files" }).click();
  const filesPanel = page.getByRole("region", { name: /Files · standard layout/ });
  await expect(filesPanel.getByText("UPLOADED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^Run import/ }).click();
  await expect(filesPanel.getByText("IN USE", { exact: true })).toBeVisible({ timeout: 90_000 });

  await page.getByRole("tab", { name: /data checklist/i }).click();
  const rejected = page.getByRole("region", { name: "Rejected rows" });
  await expect(rejected).toContainText("0 of 5 fixed");
  await expect(rejected).toContainText("The date and time cannot be read");
  await rejected.getByRole("button", { name: "Fix line 101 of mes_events.csv" }).click();
  const dialog = page.getByRole("dialog", { name: "Fix line 101 of mes_events.csv" });
  await expect(dialog).toContainText("“not a time”");

  // A value the import still cannot read is refused, with the rule, and nothing is saved.
  await dialog.getByLabel("Right value for Tijdstip").fill("yesterday");
  await dialog.getByLabel("Why (required)").fill("time typed wrong at the bench terminal");
  await dialog.getByRole("button", { name: "Save fix" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Nothing was saved");

  await dialog.getByLabel("Right value for Tijdstip").fill("20-07-2026 10:11");
  await dialog.getByRole("button", { name: "Save fix" }).click();
  await expect(dialog).toBeHidden({ timeout: 30_000 });
  await expect(rejected).toContainText("1 of 5 fixed");
  await expect(rejected).toContainText("Fixed to 20-07-2026 10:11");

  await page.goto("/data");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Plant", { exact: true }).selectOption("PLANT-F");
  const fixed = page.getByRole("region", { name: "Fixed in the app" });
  await expect(fixed).toContainText("1 in use");
  await expect(fixed).toContainText(
    "line 101 of mes_events.csv: Tijdstip “not a time” → “20-07-2026 10:11”",
  );
  await expect(fixed).toContainText("time typed wrong at the bench terminal");
  await expect(fixed.getByRole("link", { name: /Download as CSV/ })).toHaveAttribute(
    "href",
    "/api/plants/PLANT-F/corrections.csv",
  );

  await fixed.getByRole("button", { name: /^Undo: line 101 of mes_events.csv/ }).click();
  await expect(fixed).toContainText("none in use", { timeout: 30_000 });
  await expect(fixed).toContainText("the original counts again");
});
