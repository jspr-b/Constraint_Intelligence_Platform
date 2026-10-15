import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { PAGES, stubApi, stubPages } from "./api";

const ROUTES = [...PAGES.map((p) => `/${p}`), "/login", "/shift/tv"];

for (const theme of ["white", "dark"]) {
  test.describe(`${theme} theme`, () => {
    for (const route of ROUTES) {
      test(`${route} has no serious or critical axe violations`, async ({ page, context }) => {
        await context.addCookies([
          { name: "cip_theme", value: theme, url: "http://localhost:3300" },
        ]);
        await stubApi(page, { role: "it" });
        await stubPages(page);
        await page.goto(route);
        await expect(page.locator("main")).toBeVisible();
        await page.waitForLoadState("networkidle");
        await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();
        const blocking = results.violations.filter(
          (v) => v.impact === "serious" || v.impact === "critical",
        );
        expect(
          blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
        ).toEqual([]);
      });
    }
  });
}
