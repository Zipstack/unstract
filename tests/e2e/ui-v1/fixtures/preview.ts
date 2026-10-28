/**
 * Renders a page's v1 routes before the page is registered (D9: only a
 * page's final task registers it, so earlier tasks' specs need this).
 *
 *   test.use({ v1Preview: ["UN13"] });
 *
 * The mechanism comes from contract/registry.ts (`V1_PREVIEW`). Until P0-T03
 * provides one, a test that asks for a preview skips with the reason, so a
 * non-final page task can write its spec now and it turns on by itself.
 */

import type { BrowserContext, Page } from "@playwright/test";
import {
  type PageKey,
  PREVIEW_PENDING_REASON,
  type PreviewMechanism,
  V1_PREVIEW,
} from "../contract/registry.ts";
import { FRONTEND_URL } from "./env.ts";
import { test as seedTest } from "./seed.ts";

function writeStorage([storage, key, value]: [string, string, string]): void {
  const store = storage === "sessionStorage" ? sessionStorage : localStorage;
  store.setItem(key, value);
}

/** Applies the preview override for `pages` to this page's later loads. */
export async function enableV1Preview(
  page: Page,
  context: BrowserContext,
  pages: readonly PageKey[],
  mechanism: PreviewMechanism | null = V1_PREVIEW,
): Promise<void> {
  if (!mechanism) {
    throw new Error(PREVIEW_PENDING_REASON);
  }
  const value = JSON.stringify(pages);
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
        test.skip(!V1_PREVIEW, PREVIEW_PENDING_REASON);
        await enableV1Preview(page, context, v1Preview);
      }
      await use(undefined);
    },
    { auto: true },
  ],
});
