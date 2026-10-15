import { defineConfig, devices } from "@playwright/test";

/**
 * End to end against the real stack: docker compose API, database and worker (`docker compose up
 * -d db redis api worker`). Seeds a fixed synthetic tenant before the web server starts.
 */
const PORT = 3400;
export const E2E_TENANT = "0e2e0000-0000-4000-8000-000000000001";

export default defineConfig({
  testDir: "e2e-live",
  globalSetup: "./e2e-live/global-setup.ts",
  workers: 1,
  timeout: 120_000,
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: `http://localhost:${PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `pnpm build && pnpm exec next start --port ${PORT}`,
    url: `http://localhost:${PORT}/login`,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
    env: {
      CIP_ENV: "dev",
      CIP_API_URL: process.env.CIP_API_URL ?? "http://localhost:58000",
      CIP_TENANT_ID: E2E_TENANT,
    },
  },
});
