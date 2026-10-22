// Print the generated data checklist to PDF (A4), for sending to a prospect.
//   pnpm onboarding:pdf (from the repo root)   ->  var/onboarding/data-checklist.pdf (gitignored)
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "@playwright/test";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const out = join(root, "var", "onboarding");
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(pathToFileURL(join(root, "docs", "onboarding", "data-checklist.html")).href);
await page.pdf({ path: join(out, "data-checklist.pdf"), format: "A4", printBackground: true });
console.log(join("var", "onboarding", "data-checklist.pdf"));
await browser.close();
