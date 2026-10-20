/**
 * Self-test: the five-state helper drives and asserts every state, and a
 * failing state neither hangs on its held response nor passes silently.
 * Runs against the stand-in demo page, so it needs no platform and no
 * non-admin credentials (no-permission is a 403 interception).
 */

import { DIST, expect, test } from "../../fixtures/index.ts";
import { expectFiveStates, type Screen } from "../../helpers/index.ts";
import {
  DEMO_API,
  DEMO_EMPTY,
  DEMO_REST,
  DEMO_REST_TEST_ID,
  installDemoPage,
  openDemoPage,
} from "../../support/demo-page.ts";

function demoScreen(page: Parameters<typeof openDemoPage>[0]): Screen {
  return {
    open: () => openDemoPage(page),
    api: DEMO_API,
    rest: (p) => p.getByTestId(DEMO_REST_TEST_ID),
    restBody: DEMO_REST,
    emptyBody: DEMO_EMPTY,
  };
}

test.describe("harness: five states", { tag: DIST.all }, () => {
  test.beforeEach(async ({ page }) => {
    await installDemoPage(page);
  });

  test("drives rest, loading, empty, error and no-permission", async ({
    page,
  }) => {
    await expectFiveStates(page, demoScreen(page));
  });

  test("a state that never renders fails, and promptly", async ({ page }) => {
    const started = Date.now();
    const error = await expectFiveStates(page, {
      ...demoScreen(page),
      states: ["loading"],
      // A skeleton id the page never renders.
      locators: { loading: (p) => p.getByTestId("not-a-skeleton") },
      timeout: 1_000,
    }).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(Error);
    // The held response was released: the page went on to render rest.
    await expect(page.getByTestId(DEMO_REST_TEST_ID)).toBeVisible();
    expect(Date.now() - started).toBeLessThan(10_000);
  });

  test("a wrong empty body is caught", async ({ page }) => {
    const error = await expectFiveStates(page, {
      ...demoScreen(page),
      states: ["empty"],
      emptyBody: DEMO_REST,
      timeout: 1_000,
    }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(Error);
  });
});
