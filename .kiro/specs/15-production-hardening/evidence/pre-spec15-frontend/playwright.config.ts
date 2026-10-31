import { defineConfig } from "@playwright/test";

/**
 * One browser smoke test (Spec 13, OD-138) against the production build (`next start`).
 * Default: a fixture API started by the test on 127.0.0.1:18006. With E2E_LIVE_API_URL and E2E_LIVE_TOKEN the same
 * test runs against a real cji-api (the fault-injection step is skipped).
 * Uses the installed Chrome (no browser download); override with PLAYWRIGHT_CHANNEL (e.g. "msedge").
 */
export const FIXTURE_API_PORT = 18006;
const PORT = 3100;
const live = process.env.E2E_LIVE_API_URL;

export default defineConfig({
  testDir: "e2e",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    channel: process.env.PLAYWRIGHT_CHANNEL ?? "chrome",
    trace: "retain-on-failure",
  },
  webServer: {
    command: `node node_modules/next/dist/bin/next start --port ${PORT}`,
    url: `http://localhost:${PORT}/login`,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      CJI_API_BASE_URL: live ?? `http://127.0.0.1:${FIXTURE_API_PORT}`,
      CJI_SESSION_SECRET: process.env.CJI_SESSION_SECRET ?? "e2e-only-session-secret-0123456789abcdef",
      CJI_API_TIMEOUT_MS: "15000",
      NEXT_TELEMETRY_DISABLED: "1",
    },
  },
});
