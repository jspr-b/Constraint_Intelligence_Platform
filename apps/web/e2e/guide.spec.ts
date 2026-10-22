import { expect, test, type Page } from "@playwright/test";
import { stubApi } from "./api";

const steps = (upload: string, check: string) => [
  { key: "plant", state: "done", detail: null, missing: [] },
  { key: "upload", state: upload, detail: null, missing: [] },
  { key: "check", state: check, detail: null, missing: [] },
  { key: "answer", state: "later", detail: null, missing: [] },
];

async function stubOnboarding(page: Page, canSetUp: boolean, complete = false): Promise<void> {
  await page.route("**/api/onboarding*", (route) =>
    route.fulfill({
      json: {
        plant_code: "PLANT-A",
        plant_name: "Plant A (synthetic)",
        steps: complete ? steps("done", "done") : steps("todo", "todo"),
        next_step: complete ? null : "upload",
        complete,
        can_set_up: canSetUp,
        setup_contacts: ["it@plant-a.example.test"],
      },
    }),
  );
}

test("a new client sees the next step and a link to do it", async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubOnboarding(page, true);
  await page.goto("/conn");
  const guide = page.getByRole("region", { name: "Getting started" });
  await expect(guide).toBeVisible();
  await expect(guide.getByText("1 of 3 done")).toBeVisible();
  await guide.getByRole("link", { name: /upload/i }).click();
  await expect(page).toHaveURL(/\/import$/);
});

test("a role that cannot set up learns who can", async ({ page }) => {
  await stubApi(page, { role: "plant_director" });
  await stubOnboarding(page, false);
  await page.goto("/main");
  const guide = page.getByRole("region", { name: "Getting started" });
  await expect(guide.getByText(/it@plant-a\.example\.test/).first()).toBeVisible();
  await expect(guide.getByRole("link", { name: /upload/i })).toHaveCount(0);
});

test("the guide can be hidden and opened again", async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubOnboarding(page, true);
  await page.goto("/conn");
  const guide = page.getByRole("region", { name: "Getting started" });
  await guide.getByRole("button", { name: "Hide" }).click();
  await expect(guide).toHaveCount(0);
  await page.reload();
  await expect(guide).toHaveCount(0);
  await page.getByRole("button", { name: "Getting started" }).click();
  await expect(guide).toBeVisible();
});

test("the guide stays away once every step is done", async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubOnboarding(page, true, true);
  await page.goto("/conn");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("region", { name: "Getting started" })).toHaveCount(0);
});

test("a placeholder page says what it will show and what to do today", async ({ page }) => {
  await stubApi(page, { role: "coo" });
  await stubOnboarding(page, false);
  await page.goto("/loss");
  await expect(page.getByText("Coming soon")).toBeVisible();
  await expect(page.getByText(/hours and euros your bottleneck loses/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Finish getting started" })).toBeVisible();
});
