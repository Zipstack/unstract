import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the `ui` rig group (tier: e2e).
 *
 * This is the tier the 348 Vitest tests structurally cannot cover: jsdom
 * computes no layout, so overflow, positioning and visual state are
 * unobservable there. Every UI defect found during the shadcn migration — a
 * toggle rendering blank, a nav arrow anchored to the wrong month, a filter row
 * breaking on a date range — was spotted by a human in a browser.
 *
 * Run it through the rig, which boots the platform and exports the URLs:
 *   python -m tests.rig run ui
 *
 * Or standalone against an already-running stack:
 *   UNSTRACT_FRONTEND_URL=http://localhost:3000 npx playwright test
 */

/*
 * The rig exports UNSTRACT_FRONTEND_URL when it brings the platform up; the
 * fallback matches the port compose publishes the frontend on.
 *
 * Deliberately no UNSTRACT_BACKEND_URL fallback. The frontend has its own
 * origin (:3000 vs the backend's :8000), and the rig always exports the backend
 * URL — so accepting it here would silently point every spec at the API and
 * make the :3000 default unreachable in exactly the case it exists for.
 */
const baseURL = process.env.UNSTRACT_FRONTEND_URL ?? "http://localhost:3000";

export default defineConfig({
  // Specs sit beside this config; `@playwright/test` is installed here too, so
  // the suite is self-contained and resolves without reaching into frontend/.
  testDir: ".",
  /*
   * `fullyParallel` off by default: these tests drive a shared platform with
   * shared org state, so parallel specs can see each other's writes. Turn it on
   * per-file once the suite has isolation.
   */
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  /*
   * JUnit so the rig's `parse_junit` reads these results exactly like every
   * other group's. The rig sets PLAYWRIGHT_JUNIT_OUTPUT_NAME to the group's
   * junit.xml; the default keeps standalone runs from writing to the repo root.
   */
  reporter: [
    ["list"],
    [
      "junit",
      {
        outputFile:
          process.env.PLAYWRIGHT_JUNIT_OUTPUT_NAME ??
          "reports/ui/junit.xml",
      },
    ],
  ],
  use: {
    baseURL,
    // Artefacts only for failures — a green suite should leave nothing behind.
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
