import { expect, type Page } from "@playwright/test";

/** After a run the Import page opens the flow found in the data by itself (CI0005 seq 06);
 * the client then goes back to the files. */
export async function flowOpensThenFiles(page: Page): Promise<void> {
  await expect(page.getByRole("tab", { name: /Flow/, selected: true })).toBeVisible({
    timeout: 90_000,
  });
  await expect(
    page.getByRole("heading", { name: "This is the flow we found in your data" }),
  ).toBeVisible({
    timeout: 90_000,
  });
  await page.getByRole("tab", { name: /Upload files/ }).click();
}
