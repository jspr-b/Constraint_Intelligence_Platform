import { expect, test } from "@playwright/test";
import { stubApi } from "./api";

test("a term explains itself on tap and on keyboard focus", async ({ page }) => {
  await stubApi(page, { role: "coo" });
  await page.goto("/loss");
  const term = page.getByRole("main").getByRole("button", { name: "bottleneck" });
  await term.click();
  await expect(page.getByRole("tooltip")).toContainText("limits how much the whole plant");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await page.mouse.move(0, 0);
  await page.keyboard.press("Tab");
  await page.keyboard.press("Shift+Tab");
  await expect(term).toBeFocused();
  await expect(page.getByRole("tooltip")).toBeVisible();
});

test("the details drawer lists the words we use", async ({ page }) => {
  await stubApi(page, { role: "coo" });
  await page.goto("/main");
  const words = page.getByRole("region", { name: "Words we use" });
  await expect(words.getByText("Throughput", { exact: true })).toBeVisible();
  await expect(words.getByText(/sales price minus truly variable cost/)).toBeVisible();
});
