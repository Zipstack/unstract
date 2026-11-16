import { dirname, join } from "node:path";
import { defineConfig, devices } from "@playwright/test";
import { FRONTEND_URL } from "./fixtures/env.ts";
import {
  currentDistribution,
  otherDistributionsGrep,
} from "./fixtures/tags.ts";

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
 * Tests tagged for UNSTRACT_DISTRIBUTION (default `oss`) run, tests tagged
 * only for another are not collected, and untagged ones fail; see
 * fixtures/tags.ts.
 */

/** The rig points JUnit at reports/<group>/junit.xml, the tree CI uploads. */
const JUNIT = process.env.PLAYWRIGHT_JUNIT_OUTPUT_NAME;

export default defineConfig({
  testDir: ".",
  // Page specs by task id, harness self-tests, and the P8-T01 journeys.
  testMatch: ["specs/**/*.spec.ts", "journeys/**/*.spec.ts"],
  // Not collected: tests tagged only for another distribution. Untagged ones
  // still are, and fail (fixtures/tags.ts).
  grepInvert: otherDistributionsGrep(),
  /*
   * Screenshots, videos and axe results beside the group's junit.xml, so CI
   * uploads them with it; standalone runs keep Playwright's default.
   */
  outputDir: JUNIT ? join(dirname(JUNIT), "test-results") : "test-results",
  /*
   * Serial, like `ui`: specs drive one shared platform and org, so parallel
   * specs would see each other's seeded rows.
   */
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  /*
   * A test that passes only on its retry fails the run: JUnit would count it
   * as a plain pass, and an intermittent state check would never surface.
   * The retry stays, for its failure artefacts.
   */
  failOnFlakyTests: Boolean(process.env.CI),
  metadata: { distribution: currentDistribution() },
  /*
   * JUnit so the rig's `parse_junit` reads this group like every other. The
   * rig sets PLAYWRIGHT_JUNIT_OUTPUT_NAME to the group's junit.xml.
   */
  reporter: [
    ["list"],
    ["junit", { outputFile: JUNIT ?? "reports/frontend-v1-e2e/junit.xml" }],
  ],
  use: {
    baseURL: FRONTEND_URL,
    /*
     * No traces in CI: a trace records fill() values and API request bodies,
     * which on the sign-in path are the password, and outputDir is uploaded.
     * Screenshots and videos show a password field masked.
     */
    trace: process.env.CI ? "off" : "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
