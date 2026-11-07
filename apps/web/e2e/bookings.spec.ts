import { expect, test } from "@playwright/test";
import { stubApi, stubDetection, stubPages } from "./api";

/** An answer built on hour bookings says so, and what scans would add (ADR-0011 §5). */
test("an answer from hour bookings says it is less sure and what scans would add", async ({
  page,
}) => {
  await stubApi(page, { role: "production_planner" });
  await stubPages(page);
  await page.route(/\/api\/plants\/PLANT-A\/detection(\?.*)?$/, async (route) => {
    const kind = new URL(route.request().url()).searchParams.get("period_kind") ?? "all";
    const d = stubDetection(kind, "2026-07-20T04:00:00Z", false);
    const reasons = d.reasons as Record<string, unknown>[];
    await route.fulfill({
      json: {
        plant_code: "PLANT-A",
        run: {
          status: "ready",
          started_at: "2026-10-12T05:00:00Z",
          finished_at: "2026-10-12T05:01:00Z",
          period_start_at: "2026-07-20T04:00:00Z",
          period_end_at: "2026-10-09T20:00:00Z",
          error: null,
        },
        import_id: "i1",
        detections: [
          {
            ...d,
            confidence: "medium",
            reasons: [...reasons, { code: "times_from_bookings", values: { share_pct: 100 } }],
          },
        ],
      },
    });
  });
  await page.goto("/main");
  const answer = page.getByRole("region", { name: /answer/i }).first();
  await expect(answer).toContainText(
    "100% of the start and finish times come from hour bookings, not scans",
  );
  await expect(answer).toContainText("Start and finish scans per job and step would add");
});
