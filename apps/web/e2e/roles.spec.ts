import { expect, test } from "@playwright/test";
import { PAGES, stubApi } from "./api";

const PLANNER_PAGES = ["planner", "buffer", "plan", "flow", "data"];

test("role switch opens the role's start page and its menu from the access model", async ({
  page,
}) => {
  await stubApi(page, { role: "coo", pages: { planner: PLANNER_PAGES } });
  await page.goto("/main");
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByRole("link")).toHaveCount(PAGES.length);
  await page.getByRole("button", { name: /Role: COO/ }).click();
  await page.getByRole("menuitemradio", { name: "Planner" }).click();
  await expect(page).toHaveURL(/\/planner$/);
  await expect(page.getByRole("button", { name: /Role: Planner/ })).toBeVisible();
  await expect(nav.getByRole("link")).toHaveCount(PLANNER_PAGES.length);
  await expect(nav.getByRole("link", { name: "Value report" })).toHaveCount(0);
  await expect(nav.getByRole("heading", { name: "Prove" })).toHaveCount(0);
});

test("a page the role may not open says so", async ({ page }) => {
  await stubApi(page, { role: "planner", pages: { planner: PLANNER_PAGES } });
  await page.goto("/value");
  await expect(page.getByText("Your role may not open this page.")).toBeVisible();
  await expect(page.getByText("Not built yet")).toHaveCount(0);
});

test("the station role gets only the station screen, without a menu", async ({ page }) => {
  await stubApi(page, { role: "station" });
  await page.goto("/");
  await expect(page).toHaveURL(/\/station$/);
  await expect(page.getByRole("navigation")).toHaveCount(0);
  await expect(page.getByRole("complementary", { name: "Details" })).toHaveCount(0);
  await page.goto("/main");
  await expect(page.getByText("This screen belongs to a step.")).toBeVisible();
});

test("each role lands on its start page", async ({ page }) => {
  const cases: [string, string, string][] = [
    ["plant_director", "main", "Overview"],
    ["shift_lead", "shift", "Shift and floor"],
    ["it", "conn", "Connections"],
  ];
  for (const [role, start, heading] of cases) {
    await page.unrouteAll();
    await stubApi(page, { role });
    await page.goto("/");
    await expect(page).toHaveURL(new RegExp(`/${start}$`));
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  }
});

test("the shift page links to TV mode, which has no menu", async ({ page }) => {
  await stubApi(page, { role: "shift_lead" });
  await page.goto("/shift");
  await page.getByRole("link", { name: "TV mode" }).click();
  await expect(page).toHaveURL(/\/shift\/tv$/);
  await expect(page.getByRole("navigation")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Exit TV mode" })).toBeVisible();
});
