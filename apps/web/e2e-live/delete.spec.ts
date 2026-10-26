import { readdirSync } from "node:fs";
import { join } from "node:path";
import { expect, type Page, test } from "@playwright/test";

const SPLIT = join(process.cwd(), "../../data/synthetic/import_cases/split");

async function uploadAndRun(page: Page, folder: string) {
  await page.goto("/import");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Plant", { exact: true }).selectOption("PLANT-D");
  const dir = join(SPLIT, folder);
  await page
    .getByLabel("CSV or Excel exports")
    .setInputFiles(readdirSync(dir).map((f) => join(dir, f)));
  await page.getByRole("button", { name: "Upload files" }).click();
  const filesPanel = page.getByRole("region", { name: /Files · standard layout/ });
  await expect(filesPanel.getByText("UPLOADED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^Run import/ }).click();
  await expect(filesPanel.getByText("IN USE", { exact: true })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/Your numbers are calculated/)).toBeVisible({ timeout: 90_000 });
}

test("IT deletes the second upload: it shows what goes, and the first upload's data stays", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("it@e2e.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/conn$/);
  await page.goto("/setup");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Add plant" }).first().click();
  const add = page.getByRole("dialog");
  await add.getByLabel(/Short plant code/).fill("PLANT-D");
  await add.getByLabel("Name").fill("Plant A in two uploads (synthetic)");
  await add.getByRole("button", { name: "Save" }).click();
  await expect(add).toBeHidden();

  await uploadAndRun(page, "upload_1");
  await uploadAndRun(page, "upload_2");
  const history = page.getByRole("region", { name: "Import history" });

  await history
    .getByRole("button", { name: /^Delete the upload of/ })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("3,539");
  await expect(dialog).toContainText("3,545 stay");
  await dialog.getByRole("button", { name: "Delete for good" }).click();
  await expect(dialog).toBeHidden({ timeout: 60_000 });
  await expect(history.getByRole("cell", { name: /^DELETED By IT \/ ERP owner/ })).toBeVisible();
  await expect(history).toContainText("3,545 events first sent in it");
});
