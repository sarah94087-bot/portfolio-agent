import { defineConfig } from "@playwright/test";

// Browser tests against the production build, on recorded streams only: no backend, no model.
// e2e/support/fixtures.ts sends every /api/* request to a local stand-in (ADR-0017).
//
//   npm run test:e2e           builds, then runs everything
//   E2E_NO_BUILD=1 npm run test:e2e    reuses the last build

const PORT = 3217;
const start = `npx next start -p ${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0, // a flaky test here is a bug to fix, not to retry
  workers: process.env.CI ? 2 : 4,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  timeout: 30_000,
  use: {
    baseURL: `http://localhost:${PORT}`,
    browserName: "chromium",
    locale: "he-IL",
    trace: "retain-on-failure",
  },
  webServer: {
    command: process.env.E2E_NO_BUILD ? start : `npm run build && ${start}`,
    url: `http://localhost:${PORT}/he`,
    timeout: 240_000,
    reuseExistingServer: false,
    stdout: "ignore",
    stderr: "pipe",
  },
});
