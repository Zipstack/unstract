/**
 * P0-T06: v1's own session and guards (UN-4314), on P0-T03's demo page.
 *
 * v1 loads the session from v0's cookies, so a user signed in on v0 opens a
 * v1 page without signing in again. A session that ends while a v1 page is
 * open, or before it loads, lands on sign-in. The sign-out cases run on OSS,
 * where sign-in is the app's own page (cloud's is the identity provider's).
 */

import type { Page } from "@playwright/test";
import { LAST_USER_STORAGE_KEY } from "../contract/registry.ts";
import { DIST, expect, test } from "../fixtures/index.ts";

// Django's session cookie: removing it ends the session as an expiry does.
const SESSION_COOKIE = "sessionid";

async function expectOnSignIn(page: Page): Promise<void> {
  await expect
    .poll(() => new URL(page.url()).pathname, {
      message: "the app never reached sign-in",
    })
    .toBe("/landing");
  await expect(page.getByTestId("v1-demo")).toHaveCount(0);
}

test.describe("P0-T06 session: signed in on v0", { tag: DIST.all }, () => {
  test("opens the v1 demo page without signing in again", async ({
    page,
    app,
    session,
  }) => {
    await app.goto("workflows");
    await expect(page).toHaveURL(new RegExp(`/${app.orgName}/workflows`));

    // Forget what v0 recorded, so only v1's own session load can record the user.
    await page.evaluate(() => localStorage.clear());
    await app.goto("v1-demo");
    await expect(page.getByTestId("v1-demo")).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/${app.orgName}/v1-demo$`));
    await expect
      .poll(() =>
        page.evaluate(
          (key) => localStorage.getItem(key),
          LAST_USER_STORAGE_KEY,
        ),
      )
      .toBe(session.userId);
  });

  test("a URL naming another organisation goes to selection, not an error page", async ({
    page,
    app,
  }) => {
    await page.goto("/not-a-member-org/v1-demo");
    // v0's selection page sends a user who already has an organisation to it.
    await expect(page).toHaveURL(new RegExp(`/${app.orgName}/`));
    await expect(page.getByTestId("v1-demo")).toHaveCount(0);
  });
});

test.describe("P0-T06 session: ended", { tag: DIST.oss }, () => {
  test("a session that expires on a v1 page lands on sign-in", async ({
    page,
    context,
    app,
  }) => {
    await app.goto("v1-demo");
    await expect(page.getByTestId("v1-demo")).toBeVisible();

    await context.clearCookies({ name: SESSION_COOKIE });
    // The page refreshes its data when it becomes visible; that call gets the 401.
    // Bubbling, as the browser's own is: TanStack Query listens on window.
    await page.evaluate(() =>
      document.dispatchEvent(new Event("visibilitychange", { bubbles: true })),
    );
    await expectOnSignIn(page);
  });

  test("a v1 page opened with no session goes to sign-in before any data call", async ({
    page,
    context,
    app,
  }) => {
    await context.clearCookies({ name: SESSION_COOKIE });
    // The guard sends a guest away without the page asking for data, so no 401 does it.
    const dataCalls: string[] = [];
    page.on("request", (request) => {
      if (new URL(request.url()).pathname.startsWith("/api/v1/unstract/")) {
        dataCalls.push(request.url());
      }
    });
    await app.goto("v1-demo");
    await expectOnSignIn(page);
    expect(dataCalls).toEqual([]);
  });
});
