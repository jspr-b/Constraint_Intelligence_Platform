import { readdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

const CLEAN = join(process.cwd(), "../../data/synthetic/plant_a/erp_export/clean/csv");

test("a calendar edit recalculates the numbers by itself and every page says so", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("it@e2e.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/conn$/);

  // Its own plant, so the calendar edit does not change the answers the other specs check.
  await page.goto("/setup");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Add plant" }).first().click();
  const add = page.getByRole("dialog");
  await add.getByLabel(/Short plant code/).fill("PLANT-R");
  await add.getByLabel("Name").fill("Plant A refreshed (synthetic)");
  await add.getByRole("button", { name: "Save" }).click();
  await expect(add).toBeHidden();

  await page.goto("/import");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Plant", { exact: true }).selectOption("PLANT-R");
  await page
    .getByLabel("CSV or Excel exports")
    .setInputFiles(readdirSync(CLEAN).map((f) => join(CLEAN, f)));
  await page.getByRole("button", { name: "Upload files" }).click();
  const filesPanel = page.getByRole("region", { name: /Files · standard layout/ });
  await expect(filesPanel.getByText("UPLOADED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^Run import/ }).click();
  await expect(filesPanel.getByText("IN USE", { exact: true })).toBeVisible({ timeout: 90_000 });
  const banner = page.getByRole("region", { name: "Numbers and data age" });
  await expect(banner).toContainText("Plant A refreshed (synthetic) updated at", {
    timeout: 90_000,
  });

  // Maintenance on the bottleneck during production, on a day in the data: no button pressed.
  await page.goto("/calendar");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Plant", { exact: true }).selectOption("PLANT-R");
  await page.getByLabel("Day", { exact: true }).fill("2026-08-04");
  await page.getByRole("button", { name: "Add to calendar" }).click();
  const dialog = page.getByRole("dialog", { name: "Add to calendar" });
  await dialog.getByLabel("Step").selectOption("PNT-01");
  await dialog.getByLabel("Kind").selectOption("maintenance");
  await dialog.getByLabel("From").fill("10:00");
  await dialog.getByLabel("Until", { exact: true }).fill("12:00");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(banner).toContainText(
    /Plant A refreshed \(synthetic\) (because|updated at .* because) the calendar changed/,
  );
  await expect(banner).toContainText(
    /Numbers for Plant A refreshed \(synthetic\) updated at .* because the calendar changed/,
    { timeout: 90_000 },
  );

  // The other pages say it too.
  await page.goto("/main");
  await expect(banner).toContainText("because the calendar changed");
});
