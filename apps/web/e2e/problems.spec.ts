import { expect, test } from "@playwright/test";
import { stubApi, stubPages } from "./api";

test("a read that fails says so, with details folded away, and can be tried again", async ({
  page,
}) => {
  await stubApi(page, { role: "it" });
  await stubPages(page);
  let fail = true;
  await page.route("**/api/plants/PLANT-A/setup", (route) =>
    fail
      ? route.fulfill({
          status: 500,
          json: { code: "server_error", message: "Something went wrong on our side." },
        })
      : route.fallback(),
  );
  await page.goto("/setup");
  const banner = page.getByRole("alert").filter({ hasText: "Part of this page could not load." });
  await expect(banner).toBeVisible({ timeout: 15_000 });
  await expect(banner.getByText("Something went wrong on our side.")).toBeVisible();
  await expect(banner.getByText(/server_error/)).toBeHidden();
  await banner.getByText("Technical details").click();
  await expect(banner.getByText("500 /plants/PLANT-A/setup · server_error")).toBeVisible();
  fail = false;
  await banner.getByRole("button", { name: "Try again" }).click();
  await expect(banner).toHaveCount(0);
  await expect(page.getByRole("tab", { name: /Stations and machines/ })).toBeVisible();
});

test("one banner when the API is unreachable", async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubPages(page);
  await page.route("**/api/health", (route) => route.fulfill({ status: 502, body: "" }));
  await page.goto("/conn");
  await expect(page.getByText("We can't reach the server right now.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Try now" })).toBeVisible();
});

test("a refused change says it was not saved", async ({ page }) => {
  await stubApi(page, { role: "coo" });
  await page.route("**/api/access/pages", (route) =>
    route.fulfill({
      status: 409,
      json: {
        code: "page_locked",
        message: "This page cannot be turned off for this role: it is its start page.",
      },
    }),
  );
  await page.goto("/access");
  const box = page.getByRole("checkbox", { name: "Planner may open Value report" });
  await box.click();
  const banner = page.getByRole("alert").filter({ hasText: "Your change was not saved." });
  await expect(banner).toBeVisible();
  await expect(banner.getByText(/it is its start page/)).toBeVisible();
  await expect(box).toBeChecked(); // the refused change is rolled back
  await banner.getByRole("button", { name: "Close" }).click();
  await expect(banner).toHaveCount(0);
});

test("a failed import says where it stopped and what to do", async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubPages(page, {
    latestImport: { status: "failed", error: "load:ValueError", failed_step: "load" },
  });
  await page.goto("/import");
  await expect(
    page.getByText("The import stopped. The data from before stays as it was."),
  ).toBeVisible();
  await expect(page.getByText(/some values do not fit/)).toBeVisible();
});

test("starting an import while one runs explains why it did not start", async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubPages(page);
  await page.route("**/api/imports/*/run", (route) =>
    route.fulfill({
      status: 409,
      json: {
        code: "import_running",
        message: "An import for this plant is already running. Wait for it to finish.",
      },
    }),
  );
  await page.goto("/import");
  await page.getByRole("button", { name: "Run import again" }).first().click();
  await expect(page.getByText(/already running/)).toBeVisible();
});

test("an error with a next step links to it", async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubPages(page);
  await page.route("**/api/plants/PLANT-A/setup", (route) =>
    route.fulfill({
      status: 503,
      json: { code: "plant_not_found", message: "This plant does not exist (yet)." },
    }),
  );
  await page.goto("/setup");
  const banner = page.getByRole("alert").filter({ hasText: "Part of this page could not load." });
  await expect(banner.getByRole("link", { name: "Open Plant setup" })).toBeVisible({
    timeout: 15_000,
  });
});

test("the page recovers by itself when the server is back", async ({ page }) => {
  let down = true;
  await stubApi(page, { role: "it" });
  await page.route("**/api/auth/me", (route) =>
    down ? route.fulfill({ status: 502, json: {} }) : route.fallback(),
  );
  await page.goto("/conn");
  await expect(page.getByText(/We can't reach the server right now/).first()).toBeVisible();
  down = false;
  await page.getByRole("button", { name: "Try now" }).first().click();
  await expect(page.getByRole("heading", { level: 1, name: "Connections" })).toBeVisible();
});
