/**
 * Self-test: the five-state helper drives and asserts every state, and each
 * of its assertions fails when its state is wrong, without hanging on a held
 * response. Runs against the state fixture (support/state-fixture.ts), so it
 * needs no platform and no non-admin credentials (no-permission is a 403
 * interception).
 *
 * Every negative case checks the failure names the locator and the matcher
 * it expected, so a case passes only for the assertion it targets, not for
 * an unrelated error inside the helper.
 */

import type { Page } from "@playwright/test";
import { STATE_TEST_IDS } from "../../contract/v1-ui.ts";
import { DIST, expect, test } from "../../fixtures/index.ts";
import { expectFiveStates, type Screen } from "../../helpers/index.ts";
import {
  FIXTURE_API,
  FIXTURE_EMPTY,
  FIXTURE_HEADING_TEST_ID,
  FIXTURE_REST,
  FIXTURE_REST_TEST_ID,
  installStateFixture,
  openStateFixture,
} from "../../support/state-fixture.ts";

const MISSING = "never-rendered";
/** Short, so each negative case fails fast; the 5s expect default would also work. */
const STATE_TIMEOUT = 1_000;

function fixtureScreen(page: Page): Screen {
  return {
    open: () => openStateFixture(page),
    api: FIXTURE_API,
    rest: (p) => p.getByTestId(FIXTURE_REST_TEST_ID),
    restBody: FIXTURE_REST,
    emptyBody: FIXTURE_EMPTY,
    timeout: STATE_TIMEOUT,
  };
}

/** Runs the helper expecting it to fail; returns the failure text. */
async function failure(page: Page, screen: Partial<Screen>): Promise<string> {
  const error: unknown = await expectFiveStates(page, {
    ...fixtureScreen(page),
    ...screen,
  }).then(
    () => null,
    (e: unknown) => e,
  );
  expect(
    error,
    "the helper passed a screen it should have failed",
  ).toBeInstanceOf(Error);
  return String((error as Error).message);
}

test.describe("harness: five states", { tag: DIST.all }, () => {
  test.beforeEach(async ({ page }) => {
    await installStateFixture(page);
  });

  test("drives rest, loading, empty, error and no-permission", async ({
    page,
  }) => {
    await expectFiveStates(page, fixtureScreen(page));
  });

  test("an empty state list is refused, not passed", async ({ page }) => {
    await expect(
      expectFiveStates(page, { ...fixtureScreen(page), states: [] }),
    ).rejects.toThrow("`states` is empty");
  });

  test("rest: a rest view that never renders fails", async ({ page }) => {
    const message = await failure(page, {
      states: ["rest"],
      rest: (p) => p.getByTestId(MISSING),
    });
    expect(message).toContain(MISSING);
    expect(message).toContain("toBeVisible");
  });

  test("loading: a skeleton that never renders fails, on the state timeout", async ({
    page,
  }) => {
    const message = await failure(page, {
      states: ["loading"],
      locators: { loading: (p) => p.getByTestId(MISSING) },
    });
    expect(message).toContain(MISSING);
    expect(message).toContain("toBeVisible");
    // The per-state timeout was honoured, not the 5s expect default.
    expect(message).toMatch(new RegExp(`Timeout:\\s+${STATE_TIMEOUT}ms`));
    // The held response was released: the page went on to render rest.
    await expect(page.getByTestId(FIXTURE_REST_TEST_ID)).toBeVisible();
  });

  test("loading: rest showing while the response is held fails", async ({
    page,
  }) => {
    // The heading is always there, so "rest" is visible during loading too.
    const message = await failure(page, {
      states: ["loading"],
      rest: (p) => p.getByTestId(FIXTURE_HEADING_TEST_ID),
    });
    expect(message).toContain(FIXTURE_HEADING_TEST_ID);
    expect(message).toContain("toBeHidden");
  });

  test("loading: rest missing after the response is released fails", async ({
    page,
  }) => {
    // Hidden while held (passes), then still absent once released.
    const message = await failure(page, {
      states: ["loading"],
      rest: (p) => p.getByTestId(MISSING),
    });
    expect(message).toContain(MISSING);
    expect(message).toContain("toBeVisible");
  });

  test("loading: a skeleton that stays after the response is released fails", async ({
    page,
  }) => {
    const message = await failure(page, {
      states: ["loading"],
      locators: { loading: (p) => p.getByTestId(FIXTURE_HEADING_TEST_ID) },
    });
    expect(message).toContain(FIXTURE_HEADING_TEST_ID);
    expect(message).toContain("toBeHidden");
  });

  test("empty: a wrong empty body is caught", async ({ page }) => {
    const message = await failure(page, {
      states: ["empty"],
      emptyBody: FIXTURE_REST,
    });
    expect(message).toContain(STATE_TEST_IDS.empty);
    expect(message).toContain("toBeVisible");
  });

  test("error: an error view that never renders fails", async ({ page }) => {
    const message = await failure(page, {
      states: ["error"],
      locators: { error: (p) => p.getByTestId(MISSING) },
    });
    expect(message).toContain(MISSING);
    expect(message).toContain("toBeVisible");
  });

  test("no-permission: a no-permission view that never renders fails", async ({
    page,
  }) => {
    const message = await failure(page, {
      states: ["noPermission"],
      locators: { noPermission: (p) => p.getByTestId(MISSING) },
    });
    expect(message).toContain(MISSING);
    expect(message).toContain("toBeVisible");
  });

  test("an open that waits for networkidle does not hang on the held response", async ({
    page,
  }) => {
    // The shape of `app.goto`, which page specs use as `open`.
    await expectFiveStates(page, {
      ...fixtureScreen(page),
      states: ["loading"],
      open: async () => {
        await openStateFixture(page);
        await page.waitForLoadState("networkidle");
      },
    });
  });

  test("without restBody, rest falls through to the route behind it", async ({
    page,
  }) => {
    // installStateFixture's API route stands in for the real API here.
    await expectFiveStates(page, {
      ...fixtureScreen(page),
      restBody: undefined,
      states: ["rest", "loading"],
    });
  });
});
