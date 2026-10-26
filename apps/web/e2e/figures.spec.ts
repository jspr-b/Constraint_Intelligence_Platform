import { expect, test } from "@playwright/test";
import { PAGES, stubApi, stubPages } from "./api";

/**
 * Every number explained (CLAUDE.md): a number on screen must be a Figure (data-figure) or a
 * Count (data-count), which open where it comes from. Raw data shown as-is (file previews, codes,
 * dates) sits inside [data-raw]. Fails with the page and the bare numbers it found.
 */
const BARE_NUMBERS = () => {
  const NUMBER = /^[-+−]?€?\s?\d[\d.,\s]*(%|€|h|wk|min|min\/unit|rows|\/\s*\d+)?$/;
  const out: string[] = [];
  const main = document.querySelector("main");
  if (!main) return out;
  const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = (node.textContent ?? "").trim();
    const parent = node.parentElement;
    if (!text || !parent || !NUMBER.test(text)) continue;
    if (parent.closest("[data-figure],[data-count],[data-raw],[role=tablist],details,option"))
      continue;
    if (parent.closest("[hidden],[aria-hidden=true]")) continue;
    out.push(text);
  }
  return out;
};

for (const role of ["it", "coo"]) {
  test(`every number on every page opens its source (${role})`, async ({ page }) => {
    // Walks every page and tab, so it needs more than the default 30 s under a full run.
    test.setTimeout(120_000);
    await stubApi(page, { role });
    await stubPages(page);
    const found: Record<string, string[]> = {};
    for (const key of PAGES) {
      await page.goto(`/${key}`);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      const bare = await page.evaluate(BARE_NUMBERS);
      // Numbers on every tab count too.
      const tabs = page.getByRole("main").getByRole("tab");
      for (let i = 1; i < (await tabs.count()); i++) {
        await tabs.nth(i).click();
        bare.push(...(await page.evaluate(BARE_NUMBERS)));
      }
      if (bare.length) found[key] = bare;
    }
    expect(found).toEqual({});
  });
}

test("a number opens how it is calculated, and its inputs open theirs", async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubPages(page);
  await page.goto("/setup");
  await page.getByRole("tab", { name: /Products/ }).click();
  await page.getByRole("button", { name: /How is F-200 · Throughput \/unit calculated/ }).click();
  const panel = page.getByRole("region", { name: "How this is calculated" });
  await expect(panel.getByText("Sales price minus truly variable cost")).toBeVisible();
  await expect(panel.getByText(/All data in the latest import/)).toBeVisible();
  // Focus moves into the Details panel, so keyboard and screen-reader users land on it.
  await expect(page.getByRole("complementary", { name: "Details" }).locator(":focus")).toHaveCount(
    1,
  );
  await panel.getByRole("button", { name: /Back to Words we use/ }).click();
  await expect(page.getByRole("region", { name: "Words we use" })).toBeVisible();
});
