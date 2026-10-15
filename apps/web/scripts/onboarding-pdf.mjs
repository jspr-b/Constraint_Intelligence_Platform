// Print the generated data checklists to PDF (A4), for sending to a prospect.
//   pnpm onboarding:pdf (from the repo root)   ->  var/onboarding/data-checklist.{en,nl}.pdf (gitignored)
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "@playwright/test";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const out = join(root, "var", "onboarding");
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage();
for (const lang of ["en", "nl"]) {
  await page.goto(
    pathToFileURL(join(root, "docs", "onboarding", `data-checklist.${lang}.html`)).href,
  );
  await page.pdf({
    path: join(out, `data-checklist.${lang}.pdf`),
    format: "A4",
    printBackground: true,
  });
  console.log(join("var", "onboarding", `data-checklist.${lang}.pdf`));
}
await browser.close();
