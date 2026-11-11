/**
 * Human Review's old-version round trip (page 11 only, D14).
 *
 *   await expectOldVersionRoundTrip(page, "UN11", {
 *     params: { orgName: app.orgName },
 *     userId: session.userId,
 *   });
 *
 * For each v1 review route: with the preference on, the v1 URL lands on its
 * mapped v0 route and v0 renders, and that holds across a reload; with it
 * off, the v0 URL lands back on the v1 route and v1 renders.
 *
 * The preference is per user, per browser, with no backend call (P0-T03):
 * localStorage `unstract.v1.oldVersion.<userId>`. The version switch learns
 * the user from the v0 session, or before it loads from
 * `unstract.v1.lastUser`; a context signed in through the API has neither on
 * its first load, so this seeds the last user too. Any page without
 * `toggle: true` is refused, because no other page may honour it.
 */

import { expect, type Page, test } from "@playwright/test";
import {
  findEntry,
  LAST_USER_STORAGE_KEY,
  OLD_VERSION_ON,
  oldVersionStorageKey,
  type PageKey,
} from "../contract/registry.ts";
import { APP_MOUNTED_SELECTOR, V1_ROOT_SELECTOR } from "../contract/v1-ui.ts";
import { fillPattern, type RouteParams, routeRegex } from "./routes.ts";

function writePreference([lastUserKey, userId, key, value]: [
  string,
  string,
  string,
  string | null,
]): void {
  // Serialised into the page, so it must not reference anything outside.
  try {
    localStorage.setItem(lastUserKey, userId);
    if (value === null) {
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, value);
    }
  } catch {
    // about:blank has an opaque origin; the init script writes it on load.
  }
}

/** Sets or clears one user's preference now and on every later load. */
export async function setOldVersionPreference(
  page: Page,
  userId: string,
  on: boolean,
): Promise<void> {
  const args: [string, string, string, string | null] = [
    LAST_USER_STORAGE_KEY,
    userId,
    oldVersionStorageKey(userId),
    on ? OLD_VERSION_ON : null,
  ];
  // Init scripts run in order, so the latest call wins on later loads.
  await page.addInitScript(writePreference, args);
  if (page.url() !== "about:blank") {
    await page.evaluate(writePreference, args);
  }
}

export interface RoundTripOptions {
  /** Fills the `:name` segments of the page's routes. */
  params: RouteParams;
  /** The signed-in user (`session.userId`): the preference is theirs. */
  userId: string;
}

export async function expectOldVersionRoundTrip(
  page: Page,
  pageKey: PageKey,
  { params, userId }: RoundTripOptions,
): Promise<void> {
  const entry = findEntry(pageKey);
  if (!entry.toggle) {
    throw new Error(
      `${pageKey} does not honour the old-version preference; the round trip is for Human Review (toggle: true) only`,
    );
  }
  const mappings = Object.entries(entry.toV0);
  if (!mappings.length) {
    throw new Error(`${pageKey} has no v1 -> v0 mappings in the registry`);
  }
  const v1Root = page.locator(V1_ROOT_SELECTOR);
  const expectV0Rendered = async () => {
    // Before the SPA mounts there is no v1 root either; wait until it has.
    await expect(page.locator(APP_MOUNTED_SELECTOR).first()).toBeVisible();
    await page.waitForLoadState("networkidle").catch(() => null);
    await expect(v1Root).toHaveCount(0);
  };

  for (const [v1, v0] of mappings) {
    const v1Url = fillPattern(v1, params);
    const v0Url = fillPattern(v0, params);

    const on = async () => {
      await setOldVersionPreference(page, userId, true);
      await page.goto(v1Url, { waitUntil: "domcontentloaded" });
      await expect(page).toHaveURL(routeRegex(v0Url));
      await expectV0Rendered();

      await page.reload({ waitUntil: "domcontentloaded" });
      await expect(page).toHaveURL(routeRegex(v0Url));
      await expectV0Rendered();
    };
    await test.step(`old version on: ${v1} -> ${v0}`, on); // NOSONAR: steps share one page, so they run in order

    // A v1-only sub-route maps to its nearest v0 route, so the way back lands
    // on whatever v1 route that v0 route redirects to, not always on `v1`.
    const back = entry.toV1[v0];
    if (!back) {
      throw new Error(`${pageKey}: ${v0} has no v1 mapping to return to`);
    }
    const off = async () => {
      await setOldVersionPreference(page, userId, false);
      await page.goto(v0Url, { waitUntil: "domcontentloaded" });
      await expect(page).toHaveURL(routeRegex(fillPattern(back, params)));
      await expect(v1Root).toBeVisible();
    };
    await test.step(`old version off: ${v0} -> ${back}`, off); // NOSONAR: steps share one page, so they run in order
  }
}
