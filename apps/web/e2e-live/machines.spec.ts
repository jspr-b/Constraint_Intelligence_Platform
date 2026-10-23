import { expect, test } from "@playwright/test";

// Runs after import.spec.ts (files run in order, one worker): plant_a is imported by then.
test("after the import the planner sees the bottleneck on Machines, with its four checks", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("it@e2e.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/conn$/);
  await page.goto("/machines");
  const banner = page.getByRole("region", { name: "Your bottleneck" });
  await expect(banner).toContainText("PNT-01", { timeout: 90_000 });
  await expect(banner).toContainText("4 of 4 checks point at");
  await expect(banner).toContainText("high");
  await expect(banner).toContainText("Lost at the bottleneck in this period:");
  await expect(banner).toContainText(/€\d/);
  await expect(banner).toContainText("Biggest cause:");
  await banner.getByText("How we found it: 4 checks").click();
  await expect(banner.getByRole("row")).toHaveCount(5);
  await expect(page.getByRole("table").last().locator("[data-constraint]")).toContainText("PNT-01");
});

test("overview says the answer and loss shows the causes, from the real import", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("it@e2e.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/conn$/);
  await page.goto("/main");
  const answer = page.getByRole("region", { name: "The answer" });
  await expect(answer).toContainText("PNT-01", { timeout: 90_000 });
  await expect(answer).toContainText("It cost you about");
  await expect(answer).toContainText("We are sure");
  await page.goto("/loss");
  const table = page.getByRole("region", { name: /Lost at the bottleneck by cause/ });
  await expect(table.getByRole("row")).toHaveCount(5);
  await page.goto("/run");
  await expect(page.getByText("The diagnosis is complete.")).toBeVisible();
});
