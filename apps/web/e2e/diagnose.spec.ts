import { expect, test, type Page } from "@playwright/test";
import { stubApi, stubDetection, stubPages } from "./api";

async function noBottleneck(page: Page): Promise<void> {
  await page.route(/\/api\/plants\/PLANT-A\/detection(\?.*)?$/, (route) => {
    const kind = new URL(route.request().url()).searchParams.get("period_kind") ?? "all";
    route.fulfill({
      json: {
        plant_code: "PLANT-A",
        run: {
          status: "ready",
          started_at: "2026-10-13T07:16:00Z",
          finished_at: "2026-10-13T07:17:00Z",
          period_start_at: "2026-07-20T04:00:00Z",
          period_end_at: "2026-10-09T20:00:00Z",
          error: null,
        },
        import_id: "i1",
        detections: [stubDetection(kind, "2026-07-20T04:00:00Z", true)],
      },
    });
  });
}

test("overview says the answer in one sentence, how sure, the causes and the evidence", async ({
  page,
}) => {
  await stubApi(page, { role: "plant_director" });
  await stubPages(page);
  await page.goto("/main");
  const answer = page.getByRole("region", { name: "The answer" });
  await expect(answer).toContainText("Paint line (PNT-01)");
  await expect(answer).toContainText("limits your output.");
  await expect(answer).toContainText("It cost you about");
  await expect(answer).toContainText("in August 2026.");
  await expect(answer).toContainText("We are sure");
  await expect(answer).toContainText("because 4 of 4 independent checks point at it.");
  await answer.getByRole("button", { name: /€433,313/ }).click();
  await expect(page.getByRole("region", { name: "How this is calculated" })).toContainText(
    "Lost throughput = bottleneck hours lost",
  );
  const causes = page.getByRole("region", { name: /Where the time went/ });
  await expect(causes.getByRole("listitem").first()).toContainText(/setups/i);
  await expect(page.getByRole("link", { name: /How we found the bottleneck/ })).toHaveAttribute(
    "href",
    "/machines",
  );
});

test("overview for a plant without a bottleneck says the limit is demand", async ({ page }) => {
  await stubApi(page, { role: "plant_director" });
  await stubPages(page);
  await noBottleneck(page);
  await page.goto("/main");
  const answer = page.getByRole("region", { name: "The answer" });
  await expect(answer).toContainText(
    "No machine limits you: you could make more if you sold more.",
  );
  await expect(answer).toContainText("Even your busiest machine, Paint line (PNT-01)");
  await expect(page.locator("[data-constraint]")).toHaveCount(0);
});

test("loss shows causes per month and week, in euros or hours, every bar opens its sum", async ({
  page,
}) => {
  await stubApi(page, { role: "plant_director" });
  await stubPages(page);
  await page.goto("/loss");
  await expect(page.getByText(/At Paint line \(PNT-01\), setups cost the most time/)).toBeVisible();
  const table = page.getByRole("region", { name: /Lost at the bottleneck by cause/ });
  await expect(table.getByRole("row").nth(1)).toContainText("No machine limited output");
  await expect(table.getByRole("row").nth(2)).toContainText("€433,313");
  await page.getByRole("button", { name: /August 2026, setups/ }).click();
  await expect(page.getByRole("region", { name: "How this is calculated" })).toContainText(
    "Setups · August 2026",
  );
  await page.getByRole("button", { name: "Hours", exact: true }).click();
  await expect(table.getByRole("row").nth(2)).toContainText("231 h");
  await page.getByRole("button", { name: "Per week" }).click();
  await expect(table.getByRole("row")).toHaveCount(2);
});

test("loss without a bottleneck explains why there is nothing to show", async ({ page }) => {
  await stubApi(page, { role: "coo" });
  await stubPages(page);
  await noBottleneck(page);
  await page.goto("/loss");
  await expect(page.getByText("No bottleneck, so no bottleneck losses")).toBeVisible();
  await expect(page.getByRole("link", { name: "See the answer on Overview" })).toBeVisible();
});

test("diagnostic run shows each step and what to do next", async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubPages(page);
  await page.goto("/run");
  const steps = page.getByRole("list", { name: "Diagnosis steps" }).getByRole("listitem");
  await expect(steps).toHaveCount(4);
  await expect(steps.nth(2)).toContainText("Paint line (PNT-01) limits your output");
  await expect(steps.nth(3)).toContainText("Lost hours and euros per cause are calculated.");
});
