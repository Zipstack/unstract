/**
 * Renders a page's v1 routes before the page is registered (D9: only a
 * page's final task registers it, so earlier tasks' specs need this).
 *
 *   test.use({ v1Preview: ["UN13"] });
 *
 * The mechanism comes from contract/registry.ts (`V1_PREVIEW`): P0-T03's
 * localStorage override, honoured only by a VITE_V1_DEV_ROUTES=true build
 * (the E2E image). It is read once when the app loads, so it is written
 * before the test's first navigation.
 */

import type { BrowserContext, Page } from "@playwright/test";
import {
  findEntry,
  type PageKey,
  type PreviewMechanism,
  shipsIn,
  V1_PREVIEW,
} from "../contract/registry.ts";
import { FRONTEND_URL } from "./env.ts";
import { test as seedTest } from "./seed.ts";
import { currentDistribution } from "./tags.ts";

/**
 * Refuses a page the app could not render here: one not declared in PAGES,
 * or one this run's distribution does not ship, which the app's live
 * registry drops even when previewed.
 */
export function assertPreviewable(pages: readonly PageKey[]): void {
  const distribution = currentDistribution();
  for (const key of pages) {
    if (!shipsIn(findEntry(key), distribution)) {
      throw new Error(
        `v1Preview: ${key} does not ship in ${distribution}; tag the spec for its distributions instead`,
      );
    }
  }
}

function writeStorage([storage, key, value]: [string, string, string]): void {
  const store = storage === "sessionStorage" ? sessionStorage : localStorage;
  store.setItem(key, value);
}

/**
 * The stored value for `pages`. A cookie-value can't hold JSON's quotes or
 * commas (RFC 6265), so the cookie kind is URI-encoded; the app decodes it.
 */
export function previewValue(
  mechanism: PreviewMechanism,
  pages: readonly PageKey[],
): string {
  const json = JSON.stringify(pages);
  return mechanism.kind === "cookie" ? encodeURIComponent(json) : json;
}

/** Applies the preview override for `pages` to this page's later loads. */
export async function enableV1Preview(
  page: Page,
  context: BrowserContext,
  pages: readonly PageKey[],
  mechanism: PreviewMechanism = V1_PREVIEW,
): Promise<void> {
  const value = previewValue(mechanism, pages);
  if (mechanism.kind === "cookie") {
    await context.addCookies([
      { name: mechanism.name, value, url: FRONTEND_URL },
    ]);
    return;
  }
  const args: [string, string, string] = [mechanism.kind, mechanism.key, value];
  await page.addInitScript(writeStorage, args);
}

interface PreviewFixtures {
  /** Page keys to render as v1 before registration. */
  v1Preview: readonly PageKey[];
  /** Applies `v1Preview` before the test body; never used directly. */
  applyV1Preview: undefined;
}

export const test = seedTest.extend<PreviewFixtures>({
  v1Preview: [[], { option: true }],
  applyV1Preview: [
    async ({ page, context, v1Preview }, use) => {
      if (v1Preview.length) {
        assertPreviewable(v1Preview);
        await enableV1Preview(page, context, v1Preview);
      }
      await use(undefined);
    },
    { auto: true },
  ],
});
