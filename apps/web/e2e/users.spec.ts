import { expect, test, type Page } from "@playwright/test";
import { stubApi } from "./api";

const USER_ID = "00000000-0000-0000-0000-0000000000c1";
const STATION_ID = "00000000-0000-0000-0000-0000000000d1";

async function stubUsers(page: Page) {
  const accounts = {
    users: [
      {
        user_id: USER_ID,
        email: "planner@plant-a.example.test",
        role: "planner",
        plant_code: null,
        status: "active",
      },
    ],
    station_logins: [
      {
        station_login_id: STATION_ID,
        plant_code: "PLANT-A",
        resource_code: "PNT-01",
        status: "active",
      },
    ],
  };
  const calls: { method: string; path: string; body: unknown }[] = [];
  await page.route("**/api/users", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as { email: string; role: string };
      calls.push({ method: "POST", path: "/users", body });
      accounts.users.push({
        user_id: "new",
        email: body.email,
        role: body.role,
        plant_code: null,
        status: "invited",
      });
      return route.fulfill({ status: 201, json: accounts.users.at(-1) });
    }
    return route.fulfill({ json: accounts });
  });
  await page.route(/\/api\/(users|station-logins)\/[^/]+\/(disable|enable)$/, async (route) => {
    calls.push({ method: "POST", path: new URL(route.request().url()).pathname, body: null });
    return route.fulfill({ json: {} });
  });
  await page.route("**/api/station-logins", async (route) => {
    calls.push({ method: "POST", path: "/station-logins", body: route.request().postDataJSON() });
    return route.fulfill({ status: 201, json: {} });
  });
  await page.route("**/api/plants", (route) =>
    route.fulfill({
      json: [{ plant_code: "PLANT-A", name: "Plant A", timezone_iana: "Europe/Amsterdam" }],
    }),
  );
  await page.route("**/api/plants/PLANT-A/resources", (route) =>
    route.fulfill({
      json: [
        {
          resource_code: "WLD-02",
          name: "Welding 2",
          kind: "machine",
          station_code: "ST-W",
          parallel_units: 1,
        },
      ],
    }),
  );
  await page.route("**/api/auth/config?*", (route) =>
    route.fulfill({ json: { provider: "dev", tenant_name: "A" } }),
  );
  return calls;
}

test("IT sees accounts and station logins, and invites a person", async ({ page }) => {
  await stubApi(page, { role: "it" });
  const calls = await stubUsers(page);
  await page.goto("/users");
  await expect(page.getByText("1 person · 1 station")).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "planner@plant-a.example.test", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("cell", { name: "PLANT-A / PNT-01", exact: true })).toBeVisible();
  await expect(page.getByText("Company sign-in · not set up")).toBeVisible();
  await expect(
    page.getByText("Who stood at which station, or how fast a person worked."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Add person" }).click();
  const dialog = page.getByRole("dialog", { name: "Add person" });
  await expect(dialog.getByText(/No email is sent\. Tell them to sign in at http/)).toBeVisible();
  await dialog.getByLabel("Work email").fill("director@plant-a.example.test");
  await dialog.getByLabel("Role").selectOption({ label: "Plant director" });
  await dialog.getByRole("button", { name: "Add person" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByRole("cell", { name: "director@plant-a.example.test", exact: true }),
  ).toBeVisible();
  expect(calls[0]).toEqual({
    method: "POST",
    path: "/users",
    body: { email: "director@plant-a.example.test", role: "plant_director", plant_code: null },
  });
});

test("IT disables an account and adds a station login", async ({ page }) => {
  await stubApi(page, { role: "it" });
  const calls = await stubUsers(page);
  await page.goto("/users");
  await page.getByRole("button", { name: "Disable planner@plant-a.example.test" }).click();
  await expect.poll(() => calls.map((c) => c.path)).toContain(`/api/users/${USER_ID}/disable`);
  await page.getByRole("button", { name: "Add station login" }).click();
  const dialog = page.getByRole("dialog", { name: "Add station login" });
  await dialog.getByLabel("Plant").selectOption("PLANT-A");
  await dialog.getByLabel("Machine").selectOption({ label: "WLD-02 · Welding 2" });
  await dialog.getByLabel("Station PIN (4–8 digits)").fill("7395");
  await dialog.getByRole("button", { name: "Add station login" }).click();
  await expect(dialog).toHaveCount(0);
  expect(calls.at(-1)).toEqual({
    method: "POST",
    path: "/station-logins",
    body: { plant_code: "PLANT-A", resource_code: "WLD-02", pin: "7395" },
  });
});

test("other roles see the list but cannot manage logins", async ({ page }) => {
  await stubApi(page, { role: "planner" });
  await stubUsers(page);
  await page.goto("/users");
  await expect(page.getByText("Planner can see this but not manage logins.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Add person" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Disable/ })).toHaveCount(0);
});

test("adding a station login with no plant says what to do first", async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubUsers(page);
  await page.route("**/api/plants", (route) => route.fulfill({ json: [] }));
  await page.goto("/users");
  await page.getByRole("button", { name: "Add station login" }).click();
  const dialog = page.getByRole("dialog", { name: "Add station login" });
  await expect(dialog.getByText(/No plant yet\. Add your plant first/)).toBeVisible();
  await expect(dialog.getByRole("link", { name: "Go to Plant setup" })).toBeVisible();
});
