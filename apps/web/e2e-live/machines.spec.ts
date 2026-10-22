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
