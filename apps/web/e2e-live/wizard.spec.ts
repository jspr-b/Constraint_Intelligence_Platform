import { readdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

const CASE = join(process.cwd(), "../../data/synthetic/wizard_cases/exact_en");

test("IT uploads an unseen export in one go and sees what each file is", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("it@e2e.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login$/);
  // Its own plant, so nothing here changes what other specs check.
  await page.goto("/setup");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Add plant" }).first().click();
  const add = page.getByRole("dialog");
  await add.getByLabel(/Short plant code/).fill("PLANT-W");
  await add.getByLabel("Name").fill("Plant A, Exact-style export (synthetic)");
  await add.getByRole("button", { name: "Save" }).click();
  await expect(add).toBeHidden();

  await page.goto("/import");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Plant", { exact: true }).selectOption("PLANT-W");
  const files = readdirSync(CASE)
    .filter((f) => f !== "expected.yaml")
    .map((f) => join(CASE, f));
  await page.getByLabel("CSV, TXT or Excel files, or a zip").setInputFiles(files);
  await page.getByRole("button", { name: "Upload files" }).click();

  const found = page.getByRole("region", { name: "What we found" });
  await expect(found).toContainText("11 tables in 11 files");
  const minimum = found.getByRole("region", { name: "Needed to start a diagnostic" });
  await expect(minimum).toContainText("Found in ShopFloorEvents.csv");
  await expect(minimum).toContainText("Found in Resources.csv");
  await expect(minimum).toContainText("Found in Roster.csv");
  await expect(
    found.getByRole("combobox", { name: "What is in ShopFloorEvents.csv?" }),
  ).toHaveValue("events");
  await expect(found.getByRole("row").filter({ hasText: "ShopFloorEvents.csv" })).toContainText(
    "1 personal column not read",
  );
  await expect(found.getByRole("region", { name: "How the files link" })).toContainText(
    "ShopFloorEvents.csv › Resource uses the codes in Resources.csv › Resource",
  );

  // The customer list is not placed: the page asks, IT skips it.
  await expect(found.getByRole("status")).toContainText("We could not tell what one file is.");
  const customers = found.getByRole("combobox", { name: "What is in Customers.csv?" });
  await customers.selectOption({ label: "Skip this file: not needed" });
  await expect(customers).toHaveValue("skip");
  await expect(found.getByRole("status")).toHaveCount(0);
  await expect(found.getByRole("row").filter({ hasText: "Customers.csv" })).toContainText(
    "Skipped by you",
  );
  // Nothing runs yet: matching the columns of this export is the next step.
  await expect(
    page.getByText("We know what each file is. Next: answer the questions"),
  ).toBeVisible();

  // Step 2: every column of this export is clear from the data; IT checks and confirms.
  await page.getByRole("tab", { name: /Map columns/ }).click();
  const columns = page.getByRole("region", { name: "What the columns hold" });
  await expect(columns.getByRole("note")).toContainText("AI not connected.");
  await expect(
    columns.getByRole("row").filter({ hasText: "Timestamp" }).getByRole("combobox"),
  ).toHaveValue("events.at");
  await expect(columns.getByRole("row").filter({ hasText: "Employee" })).toContainText(
    "Personal: not read",
  );
  await columns.getByRole("button", { name: "Confirm this summary" }).click();
  await expect(columns).toContainText("Confirmed by IT / ERP owner");
  await expect(page.getByText("Columns confirmed. Next: the app checks your codes")).toBeVisible();
});
