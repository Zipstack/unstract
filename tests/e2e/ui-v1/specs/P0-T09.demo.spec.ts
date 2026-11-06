/**
 * P0-T09 demo: proves the harness end to end, through the rig, before any v1
 * page exists. Page specs are named the same way: `specs/<task id>.spec.ts`.
 *
 * Part 1 runs on the live platform: login, org selection, seed through the
 * API, a page that renders the seeded row, teardown. The page is v0 (no v1
 * page exists yet), so its scan is report-only.
 *
 * Part 2 runs the five states, the enforcing scan and the theme matrix on
 * the STAND-IN demo page (support/demo-page.ts, a page.route stub), because
 * P0-T03's development-only demo route does not exist yet. It proves the
 * helpers, not the version switch.
 */

import { DIST, expect, test } from "../fixtures/index.ts";
import {
  expectAccessible,
  expectFiveStates,
  forEachTheme,
} from "../helpers/index.ts";
import {
  DEMO_API,
  DEMO_EMPTY,
  DEMO_REST,
  DEMO_REST_TEST_ID,
  installDemoPage,
  openDemoPage,
} from "../support/demo-page.ts";

test.describe("P0-T09 demo: live platform", { tag: DIST.both }, () => {
  test("a seeded user sees seeded data on a live page", async ({
    page,
    app,
    session,
    seed,
  }) => {
    expect(session.orgId).toBeTruthy();

    const name = seed.name("wf");
    const workflow = await seed.create<{ id: string }>("workflow/", {
      workflow_name: name,
    });
    expect(workflow.id).toBeTruthy();

    await app.goto("workflows");
    await expect(page.getByText(name, { exact: true })).toBeVisible();

    await expectAccessible(page, { mode: "report", label: "v0-workflows" });
  });
});

test.describe(
  "P0-T09 demo: stand-in for P0-T03 dev-only demo route (page.route stub)",
  { tag: DIST.all },
  () => {
    test.beforeEach(async ({ page }) => {
      await installDemoPage(page);
    });

    test("five states", async ({ page }) => {
      await expectFiveStates(page, {
        open: () => openDemoPage(page),
        api: DEMO_API,
        rest: (p) => p.getByTestId(DEMO_REST_TEST_ID),
        restBody: DEMO_REST,
        emptyBody: DEMO_EMPTY,
      });
    });

    test("accessible in every theme", async ({ page }) => {
      await forEachTheme(page, async (theme) => {
        await openDemoPage(page);
        await expect(page.getByTestId(DEMO_REST_TEST_ID)).toBeVisible();
        await expectAccessible(page, { label: theme });
      });
    });
  },
);
