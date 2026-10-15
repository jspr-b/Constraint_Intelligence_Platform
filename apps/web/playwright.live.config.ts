import { defineConfig, devices } from "@playwright/test";

/**
 * End to end against the real stack: API, database and worker from docker compose. Seeds a fixed
 * synthetic tenant first. With CIP_E2E_BASE_URL set (e.g. the web image on :53000, started with
 * CIP_TENANT_ID = E2E_TENANT) no local web server is started.
 */
const PORT = 3400;
export const E2E_TENANT = "0e2e0000-0000-4000-8000-000000000001";
const external = process.env.CIP_E2E_BASE_URL;

export default defineConfig({
  testDir: "e2e-live",
  globalSetup: "./e2e-live/global-setup.ts",
  workers: 1,
  timeout: 120_000,
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: external ?? `http://localhost:${PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  ...(external
    ? {}
    : {
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
      }),
});
