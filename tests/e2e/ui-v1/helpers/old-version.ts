/**
 * The old-version round trip for toggle pages: Human Review (page 11, D14)
 * and its demo stand-in.
 *
 *   await expectOldVersionRoundTrip(page, "UN11", {
 *     params: { orgName: app.orgName },
 *     userId: session.userId,
 *   });
 *
 * First it opens the page and waits until the app itself records the
 * signed-in user (`unstract.v1.lastUser`), which proves the session reaches
 * the version switch. Then, for each v1 review route: with the preference on,
 * the v1 URL lands on its mapped v0 route and v0 renders, and still does
 * after a reload; with it off, the v0 URL lands back on the v1 route.
 *
 * The preference is per user, per browser, with no backend call (P0-T03):
 * localStorage `unstract.v1.oldVersion.<userId>`. It is written once on the
 * loaded page, never as an init script, so the reload checks the app's own
 * persistence. Any page without `toggle: true` is refused, because no other
 * page may honour it.
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
import { settle } from "../fixtures/settle.ts";
import type { MappingFilter } from "./redirect.ts";
import { fillPattern, type RouteParams, routeRegex } from "./routes.ts";

function writePreference([key, value]: [string, string | null]): void {
  // Serialised into the page, so it must not reference anything outside.
  if (value === null) {
    localStorage.removeItem(key);
  } else {
    localStorage.setItem(key, value);
  }
}

/**
 * Sets or clears one user's preference in the open page's storage, as the
 * Human Review control does. The page must be on the app's origin.
 */
export async function setOldVersionPreference(
  page: Page,
  userId: string,
  on: boolean,
): Promise<void> {
  if (page.url() === "about:blank") {
    throw new Error("setOldVersionPreference needs a page open on the app");
  }
  const args: [string, string | null] = [
    oldVersionStorageKey(userId),
    on ? OLD_VERSION_ON : null,
  ];
  await page.evaluate(writePreference, args);
}

/**
 * Opens the app root and waits until the app has recorded `userId` as the
 * signed-in user: the v0 session reached the version switch, which writes it
 * (stores/oldVersion). Nothing in the harness writes this key.
 *
 * The root, because the session loads only on v0 routes (PersistentLogin sits
 * inside the v0 tree). A browser whose first page is a v1 URL never records
 * the user, so the preference cannot apply there until the v1 tree loads the
 * session itself (P0-T06).
 */
export async function expectAppKnowsUser(
  page: Page,
  userId: string,
): Promise<void> {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect
    .poll(
      () =>
        page.evaluate(
          (key) => localStorage.getItem(key),
          LAST_USER_STORAGE_KEY,
        ),
      {
        message:
          "the app never recorded the signed-in user for the version switch",
      },
    )
    .toBe(userId);
}

export interface RoundTripOptions {
  /** Fills the `:name` segments of the page's routes. */
  params: RouteParams;
  /** The signed-in user (`session.userId`): the preference is theirs. */
  userId: string;
  /** Narrows the check to some v1 -> v0 mappings; must leave at least one. */
  only?: MappingFilter;
}

export async function expectOldVersionRoundTrip(
  page: Page,
  pageKey: PageKey,
  { params, userId, only = () => true }: RoundTripOptions,
): Promise<void> {
  const entry = findEntry(pageKey);
  if (!entry.toggle) {
    throw new Error(
      `${pageKey} does not honour the old-version preference; the round trip is for toggle pages (Human Review and its demo stand-in) only`,
    );
  }
  const mappings = Object.entries(entry.toV0).filter(([v1, v0]) =>
    only(v1, v0),
  );
  if (!mappings.length) {
    throw new Error(`${pageKey} has no v1 -> v0 mappings to check`);
  }
  const v1Root = page.locator(V1_ROOT_SELECTOR);
  const expectV0Rendered = async () => {
    // Before the SPA mounts there is no v1 root either; wait until it has.
    await expect(page.locator(APP_MOUNTED_SELECTOR).first()).toBeVisible();
    await settle(page);
    await expect(v1Root).toHaveCount(0);
  };

  await expectAppKnowsUser(page, userId);

  for (const [v1, v0] of mappings) {
    const v1Url = fillPattern(v1, params);
    const v0Url = fillPattern(v0, params);

    const on = async () => {
      await setOldVersionPreference(page, userId, true);
      await page.goto(v1Url, { waitUntil: "domcontentloaded" });
      await expect(page).toHaveURL(routeRegex(v0Url));
      await expectV0Rendered();

      // Nothing re-seeds storage, so this checks the app kept the choice.
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
