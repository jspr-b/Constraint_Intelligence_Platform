import { expect, test, type Page } from "@playwright/test";
import { stubApi, stubDetections, stubPages } from "./api";

const NUMBERS_AT = "2026-10-26T12:50:00Z"; // 13:50 in Amsterdam

function refresh(over: Record<string, unknown>): Record<string, unknown> {
  return {
    plant_code: "PLANT-A",
    plant_name: "Plant A (synthetic)",
    timezone_iana: "Europe/Amsterdam",
    status: "ready",
    reason: "calendar",
    changed_by_role: "planner",
    requested_at: "2026-10-26T13:03:00Z",
    numbers_at: NUMBERS_AT,
    problem: null,
    last_event_at: new Date().toISOString(),
    data_age_days: 0,
    old_after_days: 7,
    ...over,
  };
}

/** The detection says "calculating" but keeps the numbers of an earlier calculation. */
async function recalculating(page: Page, status: () => string): Promise<() => number> {
  let reads = 0;
  await page.route(/\/api\/plants\/PLANT-A\/detection(\?.*)?$/, (route) => {
    reads += 1;
    const params = new URL(route.request().url()).searchParams;
    route.fulfill({
      json: {
        plant_code: "PLANT-A",
        run: {
          status: status(),
          started_at: "2026-10-13T07:16:00Z",
          finished_at: NUMBERS_AT,
          period_start_at: "2026-07-20T04:00:00Z",
          period_end_at: "2026-10-09T20:00:00Z",
          error: null,
        },
        import_id: "i1",
        detections: stubDetections(
          params.get("period_kind") ?? "all",
          params.get("period_start_at"),
        ),
      },
    });
  });
  return () => reads;
}

test("while a calendar change is recalculated the answer stays, and updates by itself", async ({
  page,
}) => {
  await stubApi(page, { role: "plant_director" });
  await stubPages(page);
  let state = "calculating";
  const reads = await recalculating(page, () => state);
  await page.route("**/api/refresh-status", (route) =>
    route.fulfill({
      json: [
        refresh(
          state === "calculating"
            ? { status: "calculating" }
            : { numbers_at: new Date().toISOString() },
        ),
      ],
    }),
  );
  await page.goto("/main");
  const banner = page.getByRole("region", { name: "Numbers and data age" });
  await expect(banner).toContainText(
    "Recalculating the numbers for Plant A (synthetic) because the calendar changed",
  );
  await expect(banner).toContainText("keep showing the numbers from Oct 26, 13:50");
  await expect(page.getByRole("region", { name: "The answer" })).toContainText(
    "Paint line (PNT-01)",
  );
  const before = reads();
  state = "ready";
  await expect(banner).toContainText(
    /Numbers for Plant A \(synthetic\) updated at .* because the calendar changed/,
    { timeout: 10_000 },
  );
  await expect.poll(reads).toBeGreaterThan(before); // the page read the new numbers
});

test("a stuck recalculation is explained and IT retries it", async ({ page }) => {
  await stubApi(page, { role: "it" });
  await stubPages(page);
  let retried = false;
  await page.route("**/api/refresh-status", (route) =>
    route.fulfill({
      json: [
        retried
          ? refresh({ status: "calculating", reason: "retry" })
          : refresh({ status: "failed", problem: "did_not_finish" }),
      ],
    }),
  );
  await page.route("**/api/plants/PLANT-A/refresh", (route) => {
    retried = true;
    route.fulfill({ status: 202, json: refresh({ status: "calculating", reason: "retry" }) });
  });
  await page.goto("/main");
  const banner = page.getByRole("region", { name: "Numbers and data age" });
  await expect(banner.getByRole("alert")).toContainText(
    "could not be recalculated after the calendar changed (by Planner). The calculation did not finish in time.",
  );
  await expect(banner).toContainText("still show the older numbers from Oct 26, 13:50");
  await banner.getByRole("button", { name: "Retry now" }).click();
  await expect(banner).toContainText("because a retry was asked for");
});

test("the director sees a failed recalculation without a retry, and who to ask", async ({
  page,
}) => {
  await stubApi(page, { role: "plant_director" });
  await stubPages(page);
  await page.route("**/api/refresh-status", (route) =>
    route.fulfill({ json: [refresh({ status: "failed", problem: "error" })] }),
  );
  await page.goto("/main");
  const banner = page.getByRole("region", { name: "Numbers and data age" });
  await expect(banner).toContainText("Ask your IT / ERP owner or planner to retry.");
  await expect(banner.getByRole("button", { name: "Retry now" })).toHaveCount(0);
});

test("old data says how old and where to upload new events", async ({ page }) => {
  await stubApi(page, { role: "planner", pages: { planner: ["main", "import"] } });
  await stubPages(page);
  await page.route("**/api/refresh-status", (route) =>
    route.fulfill({
      json: [
        refresh({
          numbers_at: "2026-10-01T10:00:00Z",
          last_event_at: "2026-10-09T20:00:00Z",
          data_age_days: 16,
        }),
      ],
    }),
  );
  await page.goto("/main");
  const banner = page.getByRole("region", { name: "Numbers and data age" });
  await expect(banner).toContainText(
    "The newest data for Plant A (synthetic) is from Oct 9, 2026, 16 days ago.",
  );
  await expect(
    banner.getByRole("link", { name: "Upload new events to see the plant as it is now." }),
  ).toHaveAttribute("href", "/import");
});

test("several plants with old data share one line", async ({ page }) => {
  await stubApi(page, { role: "plant_director" });
  await stubPages(page);
  const old = { last_event_at: "2026-10-09T20:00:00Z", data_age_days: 16 };
  await page.route("**/api/refresh-status", (route) =>
    route.fulfill({
      json: [
        refresh({ ...old, numbers_at: "2026-10-01T10:00:00Z" }),
        refresh({
          ...old,
          plant_code: "PLANT-B",
          plant_name: "Plant B (synthetic)",
          numbers_at: "2026-10-01T10:00:00Z",
        }),
      ],
    }),
  );
  await page.goto("/main");
  const banner = page.getByRole("region", { name: "Numbers and data age" });
  await expect(banner).toContainText(
    "The data is more than 7 days old for: Plant A (synthetic) (newest Oct 9, 2026); Plant B (synthetic) (newest Oct 9, 2026).",
  );
  await expect(banner.getByText(/^The newest data for/)).toHaveCount(0);
});
