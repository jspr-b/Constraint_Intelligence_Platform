import { defineConfig, devices } from "@playwright/test";

const PORT = 3300;

/** E2E against a production build. The browser's /api calls are stubbed per test (e2e/api.ts). */
export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  // Axe on every route in both themes is heavy; a few workers keep runs stable on laptops.
  workers: process.env.CI ? 2 : 3,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: `http://localhost:${PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `pnpm build && pnpm exec next start --port ${PORT}`,
    url: `http://localhost:${PORT}/login`,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
    env: {
      CIP_ENV: "test",
      CIP_API_URL: "http://127.0.0.1:9",
      CIP_TENANT_ID: "00000000-0000-0000-0000-0000000000a1",
    },
  },
});
