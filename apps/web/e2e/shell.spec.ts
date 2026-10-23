import { expect, test } from "@playwright/test";
import { stubApi } from "./api";

test.beforeEach(async ({ page }) => {
  await stubApi(page);
});

test("shell loads on the role's start page with the API status", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/main$/);
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
  await expect(page.getByRole("status")).toHaveText(/Connected/);
  await expect(page.getByRole("complementary", { name: "Details" })).toBeVisible();
});

test("keyboard moves through the nav rail and opens a page", async ({ page }) => {
  await page.goto("/main");
  const nav = page.getByRole("navigation", { name: "Main" });
  await nav.getByRole("link", { name: "Diagnostic run" }).focus();
  for (let i = 0; i < 3; i++) await page.keyboard.press("Tab");
  await expect(nav.getByRole("link", { name: "Loss" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/loss$/);
  await expect(nav.getByRole("link", { name: "Loss" })).toHaveAttribute("aria-current", "page");
});

test("theme toggle switches to dark and survives a reload", async ({ page }) => {
  await page.goto("/main");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "white");
  await page.getByRole("button", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");
});

test("an unknown page shows not found", async ({ page }) => {
  await page.goto("/does-not-exist");
  await expect(page.getByText("Page not found")).toBeVisible();
});
