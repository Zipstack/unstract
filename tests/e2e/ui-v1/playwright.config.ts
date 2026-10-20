import { defineConfig, devices } from "@playwright/test";
import { FRONTEND_URL } from "./fixtures/env.ts";
import { currentDistribution, distributionGrep } from "./fixtures/tags.ts";

/**
 * Playwright config for the `frontend-v1-e2e` rig group: the v1 frontend's
 * E2E suite, kept apart from the v0 `ui` group in tests/e2e/ui (D10, and
 * constraint 12: v1 never pollutes v0 results).
 *
 * Through the rig, which boots the platform and exports the URLs:
 *   python -m tests.rig run frontend-v1-e2e
 *
 * Standalone against a running stack:
 *   UNSTRACT_FRONTEND_URL=http://localhost:3000 bunx playwright test
 *
 * Only tests tagged for UNSTRACT_DISTRIBUTION (default `oss`) run; see
 * fixtures/tags.ts.
 */

export default defineConfig({
  testDir: ".",
  // Page specs by task id, harness self-tests, and the P8-T01 journeys.
  testMatch: ["specs/**/*.spec.ts", "journeys/**/*.spec.ts"],
  grep: distributionGrep(),
  /*
   * Serial, like `ui`: specs drive one shared platform and org, so parallel
   * specs would see each other's seeded rows.
   */
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  metadata: { distribution: currentDistribution() },
  /*
   * JUnit so the rig's `parse_junit` reads this group like every other. The
   * rig sets PLAYWRIGHT_JUNIT_OUTPUT_NAME to the group's junit.xml.
   */
  reporter: [
    ["list"],
    [
      "junit",
      {
        outputFile:
          process.env.PLAYWRIGHT_JUNIT_OUTPUT_NAME ??
          "reports/frontend-v1-e2e/junit.xml",
      },
    ],
  ],
  use: {
    baseURL: FRONTEND_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
