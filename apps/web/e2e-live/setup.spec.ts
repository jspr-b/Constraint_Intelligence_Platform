import { expect, test } from "@playwright/test";

// Setup and Calendar edits are kept through later imports (ADR-0010), so these run after the
// answer and data quality checks (machines, quality), which read the plant as imported.

test("plant setup shows engine numbers from the import and takes kick-off entries", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("it@e2e.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/conn$/);
  await page.goto("/setup");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText(/6 steps/)).toBeVisible();

  await page.getByRole("tab", { name: "Operations" }).click();
  const measured = page.getByRole("button", { name: /min\/unit/ }).first();
  await measured.click();
  await expect(page.getByRole("region", { name: "How this is calculated" })).toContainText(
    "task_time_median_v1",
  );

  await page.getByRole("tab", { name: "Products" }).click();
  const throughput = page.getByRole("button", { name: /Throughput \/unit calculated/ }).first();
  await throughput.click();
  await expect(page.getByRole("region", { name: "How this is calculated" })).toContainText(
    "throughput_per_unit_v1",
  );

  await page.getByRole("tab", { name: "Stations and steps" }).click();
  await page.getByRole("button", { name: "Add station" }).click();
  let dialog = page.getByRole("dialog", { name: "Add station" });
  await dialog.getByLabel("Station code").fill("qa");
  await dialog.getByLabel("Station name").fill("Quality check");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: /Quality check/ })).toBeVisible();

  await page.getByRole("button", { name: "Add step" }).click();
  dialog = page.getByRole("dialog", { name: "Add step" });
  await dialog.getByLabel("Step code").fill("qa-01");
  await dialog.getByLabel("Step name").fill("Inspection bench");
  await dialog.getByLabel("Station").selectOption("QA");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/7 steps/)).toBeVisible();

  await page.getByRole("tab", { name: "Capacity costs" }).click();
  await page.getByRole("button", { name: "Edit costs PNT-01" }).click();
  dialog = page.getByRole("dialog", { name: "Edit costs PNT-01" });
  await dialog.getByLabel("Overtime € /hour").fill("62,50");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("row").filter({ hasText: "PNT-01" })).toContainText("€62.50");
});

test("capacity calendar: timeline, covered break, maintenance and overtime", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("it@e2e.example.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/conn$/);
  await page.goto("/calendar");
  await page.waitForLoadState("networkidle");
  const paint = page.getByRole("list", { name: "PNT-01" });
  await expect(paint.getByRole("listitem").first()).toBeAttached();

  // The page opens on today; a weekend day has no shifts, so open the next working day.
  const workday = new Date();
  while ([0, 6].includes(workday.getDay())) workday.setDate(workday.getDate() + 1);
  const iso = `${workday.getFullYear()}-${String(workday.getMonth() + 1).padStart(2, "0")}-${String(workday.getDate()).padStart(2, "0")}`;
  await page.getByLabel("Day", { exact: true }).fill(iso);
  const lunch = paint.getByRole("button", { name: /^Break: the step stops/ }).first();
  await expect(lunch).toBeVisible();
  const name = (await lunch.getAttribute("aria-label")) ?? "";
  const time = name.replace(/^Break: the step stops /, "").split(".")[0] ?? "";
  await lunch.click();
  await expect(
    paint.getByRole("button", { name: new RegExp(`^Break covered: keeps running ${time}`) }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Add to calendar" }).click();
  const dialog = page.getByRole("dialog", { name: "Add to calendar" });
  await dialog.getByLabel("Step").selectOption("PNT-01");
  await dialog.getByLabel("Kind").selectOption("maintenance");
  await dialog.getByLabel("From").fill("18:00");
  await dialog.getByLabel("Until", { exact: true }).fill("22:00");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(
    page
      .getByRole("region", { name: /Exceptions/ })
      .getByRole("row")
      .filter({ hasText: "PNT-01" })
      .filter({ hasText: /18:00/ })
      .filter({ hasText: "Maintenance" }),
  ).toHaveCount(1);

  await page.getByRole("button", { name: "Enter overtime" }).click();
  const overtime = page.getByRole("dialog", { name: "Enter overtime" });
  await overtime.getByLabel("Step").selectOption("PNT-01");
  await overtime.getByLabel("Week").fill("42");
  await overtime.getByLabel("Hours").fill("6,5");
  await overtime.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("region", { name: /Overtime worked/ })).toContainText("6.5 h");
});
