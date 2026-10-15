import { expect, test, type Page } from "@playwright/test";
import { stubApi } from "./api";

const TENANT = "00000000-0000-0000-0000-0000000000a1";

async function stubSignIn(page: Page, provider: "dev" | "oidc") {
  await page.route("**/api/auth/config?*", (route) =>
    route.fulfill({ json: { provider, tenant_name: "Plant A (synthetic)" } }),
  );
  await page.route("**/api/auth/stations?*", (route) =>
    route.fulfill({
      json: [
        { plant_code: "PLANT-A", resource_code: "PNT-01", resource_name: "Paint line" },
        { plant_code: "PLANT-A", resource_code: "WLD-02", resource_name: "Welding 2" },
      ],
    }),
  );
}

test("personal sign-in opens the role's start page", async ({ page }) => {
  await stubSignIn(page, "dev");
  let body: unknown;
  await page.route("**/api/auth/dev-login", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({ status: 204 });
  });
  await stubApi(page, { role: "planner" });
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in to Plant A (synthetic)" })).toBeVisible();
  await page.getByLabel("Work email").fill("planner@plant-a.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/planner$/);
  expect(body).toEqual({ tenant_id: TENANT, email: "planner@plant-a.example.test" });
});

test("station sign-in opens the station screen", async ({ page }) => {
  await stubSignIn(page, "dev");
  let body: unknown;
  await page.route("**/api/auth/station-login", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({ status: 204 });
  });
  await stubApi(page, { role: "station" });
  await page.goto("/login");
  await page.getByRole("tab", { name: "Station" }).click();
  await page.getByLabel("Which station is this?").selectOption({ label: "WLD-02 · Welding 2" });
  await page.getByLabel("Station PIN").fill("4821");
  await page.getByRole("button", { name: "Open station screen" }).click();
  await expect(page).toHaveURL(/\/station$/);
  await expect(page.getByRole("navigation")).toHaveCount(0);
  expect(body).toEqual({
    tenant_id: TENANT,
    plant_code: "PLANT-A",
    resource_code: "WLD-02",
    pin: "4821",
  });
});

test("a wrong PIN shows an error and stays on the page", async ({ page }) => {
  await stubSignIn(page, "dev");
  await page.route("**/api/auth/station-login", (route) =>
    route.fulfill({ status: 401, json: {} }),
  );
  await page.goto("/login");
  await page.getByRole("tab", { name: "Station" }).click();
  await page.getByLabel("Station PIN").fill("0000");
  await page.getByRole("button", { name: "Open station screen" }).click();
  await expect(page.getByRole("alert").filter({ hasText: /Sign-in failed/ })).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test("with Keycloak configured, personal sign-in is the company account button", async ({
  page,
}) => {
  await stubSignIn(page, "oidc");
  await page.goto("/login");
  await expect(
    page.getByRole("link", { name: "Sign in with your company account" }),
  ).toHaveAttribute("href", "/auth/oidc/start");
  await expect(page.getByLabel("Work email")).toHaveCount(0);
});

test("a failed company sign-in comes back with a message", async ({ page }) => {
  await stubSignIn(page, "oidc");
  await page.goto("/auth/oidc/start");
  await expect(page).toHaveURL(/\/login\?error=sso$/);
  await expect(page.getByRole("alert").filter({ hasText: /Company sign-in failed/ })).toBeVisible();
});

test("the login page works in Dutch", async ({ page }) => {
  await stubSignIn(page, "dev");
  await page.goto("/login");
  await page.getByRole("button", { name: "nl" }).click();
  await expect(
    page.getByRole("heading", { name: "Inloggen bij Plant A (synthetic)" }),
  ).toBeVisible();
  await expect(page.getByRole("tab", { name: "Persoonlijk" })).toBeVisible();
});

test("signed out, the shell sends you to the login page", async ({ page }) => {
  await stubSignIn(page, "dev");
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 401, json: {} }));
  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.goto("/main");
  await expect(page).toHaveURL(/\/login$/);
});
