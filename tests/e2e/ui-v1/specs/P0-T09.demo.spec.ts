/**
 * P0-T09 demo: proves the harness end to end, through the rig. Page specs are
 * named the same way: `specs/<task id>.spec.ts`.
 *
 * Part 1 runs on the live platform: login, org selection, seed through the
 * API, a page that renders the seeded row, teardown. The page is v0, so its
 * scan is report-only.
 *
 * Part 2 runs on P0-T03's development-only demo pages, which the E2E image
 * registers (VITE_V1_DEV_ROUTES=true): the version switch and its redirect,
 * the theme matrix with an enforcing scan, and Human Review's old-version
 * round trip on its stand-in. The demo pages load no data, so the five-state
 * helper is proven by its self-tests (specs/harness/five-states.spec.ts).
 *
 * The redirect and the round trip also run in specs/harness/
 * registry-routes.spec.ts, once per registered page. They stay here too, at
 * the cost of two browser flows, because this file is the worked example a
 * page spec is copied from.
 */

import { V1_ROOT_SELECTOR } from "../contract/v1-ui.ts";
import { DIST, expect, test } from "../fixtures/index.ts";
import {
  expectAccessible,
  expectAppKnowsUser,
  expectOldVersionRoundTrip,
  expectV0RedirectsToV1,
  forEachTheme,
} from "../helpers/index.ts";
import { routeRegex } from "../helpers/routes.ts";

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

test.describe("P0-T09 demo: P0-T03 demo pages", { tag: DIST.all }, () => {
  test("the demo page renders as v1, and its v0 URL redirects to it", async ({
    page,
    app,
  }) => {
    await expectV0RedirectsToV1(page, "DEMO-PAGE", { orgName: app.orgName });
    await expect(page.getByTestId("v1-demo")).toBeVisible();
    await expect(page.getByTestId("v0-demo")).toHaveCount(0);
  });

  test("accessible in every theme", async ({ page, app }) => {
    await forEachTheme(page, async (theme) => {
      await app.goto("v1-demo");
      await expect(page.getByTestId("v1-demo")).toBeVisible();
      await expectAccessible(page, { label: theme });
    });
  });

  test("Human Review's stand-in: old-version round trip", async ({
    page,
    app,
    session,
  }) => {
    await expectOldVersionRoundTrip(page, "DEMO-REVIEW", {
      params: { orgName: app.orgName },
      userId: session.userId,
    });
  });

  test("Human Review's stand-in: the in-page switch goes both ways without a reload", async ({
    page,
    app,
    session,
  }) => {
    const org = encodeURIComponent(app.orgName);
    // The control needs the user, which the app records from the v0 session.
    await expectAppKnowsUser(page, session.userId);
    await app.goto("v1-demo-review/details");
    await expect(page.getByTestId("v1-demo-review")).toBeVisible();
    // A full reload would discard this marker.
    await page.evaluate(() => {
      (window as { e2eNoReload?: boolean }).e2eNoReload = true;
    });

    await page.getByRole("button", { name: "Switch to old version" }).click();
    // The v1-only sub-route maps back to the nearest v0 route.
    await expect(page).toHaveURL(routeRegex(`/${org}/v0-demo-review`));
    await expect(page.getByTestId("v0-demo-review")).toBeVisible();
    await expect(page.locator(V1_ROOT_SELECTOR)).toHaveCount(0);

    await page.getByRole("button", { name: "Switch to new version" }).click();
    await expect(page).toHaveURL(routeRegex(`/${org}/v1-demo-review`));
    await expect(page.getByTestId("v1-demo-review")).toBeVisible();
    expect(
      await page.evaluate(
        () => (window as { e2eNoReload?: boolean }).e2eNoReload,
      ),
    ).toBe(true);
  });
});
