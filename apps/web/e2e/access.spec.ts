import { expect, test, type Page } from "@playwright/test";
import { DECISIONS, PAGES, START, stubApi } from "./api";

const ALL_DECISIONS = [
  "accept_exploit_subordinate",
  "approve_elevate",
  "release_expedite",
  "report_stop",
  "edit_setup_calendar",
  "import_run_diagnostic",
  "sign_off_value",
  "manage_logins",
  "change_access",
];

/** A stateful /api/access like the real one: PUTs and presets change the matrix. */
async function stubAccess(page: Page) {
  const roles = Object.keys(START).map((role) => ({
    role,
    start_page: START[role],
    pages: [...PAGES],
    money: "eur",
    plants: "all",
    decisions: [...(DECISIONS[role] ?? [])],
  }));
  const calls: { path: string; body: unknown }[] = [];
  const roleOf = (name: string) => {
    const found = roles.find((x) => x.role === name);
    if (!found) throw new Error(`unknown role ${name}`);
    return found;
  };
  const matrix = () => ({
    pages: PAGES,
    decisions: ALL_DECISIONS,
    roles,
    locked_pages: Object.fromEntries(Object.entries(START).map(([r, p]) => [r, [p]])),
    locked_decisions: ["manage_logins", "change_access"],
  });
  await page.route("**/api/access", (route) => route.fulfill({ json: matrix() }));
  await page.route("**/api/access/pages", async (route) => {
    const body = route.request().postDataJSON() as { role: string; page: string; allowed: boolean };
    calls.push({ path: "pages", body });
    const r = roleOf(body.role);
    r.pages = body.allowed ? [...r.pages, body.page] : r.pages.filter((p) => p !== body.page);
    await route.fulfill({ json: matrix() });
  });
  await page.route("**/api/access/data", async (route) => {
    const body = route.request().postDataJSON() as { role: string; money: string; plants: string };
    calls.push({ path: "data", body });
    Object.assign(roleOf(body.role), { money: body.money, plants: body.plants });
    await route.fulfill({ json: matrix() });
  });
  await page.route("**/api/access/presets/*", async (route) => {
    const preset = new URL(route.request().url()).pathname.split("/").at(-1);
    calls.push({ path: `preset:${preset}`, body: null });
    if (preset === "role_menus") roleOf("station").pages = ["station"];
    await route.fulfill({ json: matrix() });
  });
  return calls;
}

test("the COO restricts a page and the counts update", async ({ page }) => {
  await stubApi(page, { role: "coo" });
  const calls = await stubAccess(page);
  await page.goto("/access");
  await expect(page.getByText("Everyone can open every page.")).toBeVisible();
  await expect(page.getByText("Which plant needs attention?")).toBeVisible();
  const box = page.getByRole("checkbox", { name: "Planner may open Value report" });
  await expect(box).toBeChecked();
  await box.uncheck();
  await expect(box).not.toBeChecked();
  await expect(page.getByText("1 page permission restricted.")).toBeVisible();
  expect(calls[0]).toEqual({
    path: "pages",
    body: { role: "planner", page: "value", allowed: false },
  });
  await expect(
    page.getByRole("checkbox", { name: "Planner may open Planner today" }),
  ).toBeDisabled();
});

test("the COO applies the role-menus preset and sets money to hours", async ({ page }) => {
  await stubApi(page, { role: "coo" });
  const calls = await stubAccess(page);
  await page.goto("/access");
  await page.getByRole("button", { name: "Role menus only" }).click();
  await expect(
    page.getByRole("checkbox", { name: "Station (operators) may open Overview" }),
  ).not.toBeChecked();
  await page.getByRole("tab", { name: "Data" }).click();
  await page.getByLabel("Money for Shift lead").selectOption("hours");
  await expect
    .poll(() => calls.at(-1))
    .toEqual({
      path: "data",
      body: { role: "shift_lead", money: "hours", plants: "all" },
    });
  await page.getByRole("tab", { name: "Decisions" }).click();
  await expect(
    page.getByRole("checkbox", { name: "IT / ERP owner may Manage logins (IT only)" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("checkbox", { name: "Planner may Approve Elevate actions (they cost money)" }),
  ).toBeEnabled();
});

test("other roles see access read-only", async ({ page }) => {
  await stubApi(page, { role: "planner" });
  await stubAccess(page);
  await page.goto("/access");
  await expect(page.getByText("Only the COO changes access.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Role menus only" })).toHaveCount(0);
  await expect(
    page.getByRole("checkbox", { name: "Planner may open Value report" }),
  ).toBeDisabled();
});
