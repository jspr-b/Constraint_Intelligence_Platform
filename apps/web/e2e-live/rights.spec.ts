import { readdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const BROKEN = join(process.cwd(), "../../data/synthetic/import_cases/broken/upload_1");

async function signIn(page: Page, email: string): Promise<void> {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Work email").fill(email);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

test("the COO leaves fixing rows to IT; the planner sees why and who can", async ({ page }) => {
  await signIn(page, "it@e2e.example.test");
  // Its own plant with rejected rows, so nothing here changes what other specs check.
  await page.goto("/setup");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Add plant" }).first().click();
  const add = page.getByRole("dialog");
  await add.getByLabel(/Short plant code/).fill("PLANT-G");
  await add.getByLabel("Name").fill("Plant A, rights check (synthetic)");
  await add.getByRole("button", { name: "Save" }).click();
  await expect(add).toBeHidden();
  await page.goto("/import");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Plant", { exact: true }).selectOption("PLANT-G");
  await page
    .getByLabel("CSV or Excel exports")
    .setInputFiles(readdirSync(BROKEN).map((f) => join(BROKEN, f)));
  await page.getByRole("button", { name: "Upload files" }).click();
  const filesPanel = page.getByRole("region", { name: /Files · standard layout/ });
  await expect(filesPanel.getByText("UPLOADED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^Run import/ }).click();
  await expect(filesPanel.getByText("IN USE", { exact: true })).toBeVisible({ timeout: 90_000 });

  for (const [email, role] of [
    ["coo@e2e.example.test", "COO"],
    ["planner@e2e.example.test", "Planner"],
  ] as const) {
    await page.goto("/users");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "Add person" }).click();
    const person = page.getByRole("dialog", { name: "Add person" });
    await person.getByLabel("Work email").fill(email);
    await person.getByLabel("Role").selectOption({ label: role });
    await person.getByRole("button", { name: "Add person" }).click();
    await expect(page.getByRole("cell", { name: email, exact: true })).toBeVisible();
  }

  await signIn(page, "coo@e2e.example.test");
  await page.goto("/access");
  await page.getByRole("tab", { name: "Decisions" }).click();
  const fix = page.getByRole("checkbox", {
    name: "Planner may Fix rows in the app (and undo a fix)",
  });
  await expect(fix).toBeChecked();
  // The box changes once the server has saved, so click and wait (uncheck() checks at once).
  await fix.click();
  await expect(fix).not.toBeChecked();

  await signIn(page, "planner@e2e.example.test");
  await page.goto("/import");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Plant", { exact: true }).selectOption("PLANT-G");
  await page.getByRole("tab", { name: /data checklist/i }).click();
  const rejected = page.getByRole("region", { name: "Rejected rows" });
  await expect(rejected).toContainText("0 of 5 fixed");
  await expect(rejected.getByRole("button", { name: /^Fix line/ })).toHaveCount(0);
  await expect(rejected).toContainText(
    "Planner can see this but not fix rows in the app. IT / ERP owner can.",
  );
  // Deleting imports stays with the planner: only fixing rows moved.
  await expect(
    page.getByRole("region", { name: "Import history" }).getByRole("button", { name: /^Delete/ }),
  ).not.toHaveCount(0);
});
