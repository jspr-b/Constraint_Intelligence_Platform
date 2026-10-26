import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

const ERP = join(process.cwd(), "../../data/synthetic/plant_a/erp_export");
const known = JSON.parse(readFileSync(join(ERP, "defects/defects.json"), "utf8")) as {
  missing_end_events: number;
  unknown_machine_code_rows: number;
  scrap_rows_removed: number;
};

test("import plant_a with known defects, then Data quality shows the score and the gaps", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("it@e2e.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/conn$/);

  // Its own plant: on PLANT-A this export would add to the clean events there (ADR-0010).
  await page.goto("/setup");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Add plant" }).first().click();
  const add = page.getByRole("dialog");
  await add.getByLabel(/Short plant code/).fill("PLANT-Q");
  await add.getByLabel("Name").fill("Plant A with defects (synthetic)");
  await add.getByRole("button", { name: "Save" }).click();
  await expect(add).toBeHidden();

  await page.goto("/import");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Plant", { exact: true }).selectOption("PLANT-Q");
  await expect(page.getByText("No import for this plant yet.")).toBeVisible();
  const csv = join(ERP, "defects/csv");
  await page
    .getByLabel("CSV or Excel exports")
    .setInputFiles(readdirSync(csv).map((f) => join(csv, f)));
  await page.getByRole("button", { name: "Upload files" }).click();
  const filesPanel = page.getByRole("region", { name: /Files · standard layout/ });
  await expect(filesPanel.getByText("UPLOADED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^Run import/ }).click();
  await expect(filesPanel.getByText("IN USE", { exact: true })).toBeVisible({ timeout: 90_000 });

  await page.getByRole("tab", { name: /data checklist/i }).click();
  const results = page.getByRole("region", { name: "Results per file" });
  const eventsResult = results.getByRole("row").filter({ hasText: "mes_events.csv" });
  await expect(eventsResult).toContainText("Imported, some rows rejected");
  await expect(eventsResult).toContainText(`unknown: ${known.unknown_machine_code_rows} (lines`);

  await page.goto("/data");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Plant", { exact: true }).selectOption("PLANT-Q");
  const score = page.getByRole("region", { name: "Data quality score" });
  await expect(score).toContainText("45");
  await score.getByRole("button").click();
  await expect(page.getByRole("region", { name: "How this is calculated" })).toContainText(
    "data_quality_score_v1",
  );
  await expect(page.getByRole("region", { name: "Rows imported" })).toContainText(
    `${known.unknown_machine_code_rows} rejected`,
  );

  const files = page.getByRole("region", { name: "Files" }).last();
  const events = files.getByRole("row").filter({ hasText: "events.csv" });
  await expect(events).toContainText(String(known.unknown_machine_code_rows));
  await expect(events).toContainText("Unknown code");

  const gaps = page.getByRole("region", { name: "Gaps and their effect on the results" });
  await expect(gaps).toContainText("MISSING IS SHOWN AS MISSING");
  await expect(
    gaps.getByRole("row").filter({ hasText: "No scrap recorded anywhere" }),
  ).toContainText("Medium");
  const unpaired = await gaps
    .getByRole("row")
    .filter({ hasText: "have no end event" })
    .allTextContents();
  const total = unpaired.reduce(
    (n, row) => n + Number(/(\d+) start events/.exec(row)?.[1] ?? 0),
    0,
  );
  expect(total).toBeGreaterThanOrEqual(known.missing_end_events);
  expect(total).toBeLessThanOrEqual(known.missing_end_events + known.unknown_machine_code_rows);
});
