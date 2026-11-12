import type { Page } from "@playwright/test";

/**
 * How long to wait for the network to go quiet before carrying on anyway.
 * The config sets no navigation timeout, so without one a screen that keeps
 * a request open (polling) would hold the wait until the test times out.
 */
export const SETTLE_TIMEOUT_MS = 10_000;

/** Waits briefly for the network to go idle; carries on if it doesn't. */
export async function settle(page: Page): Promise<void> {
  await page
    .waitForLoadState("networkidle", { timeout: SETTLE_TIMEOUT_MS })
    .catch(() => null);
}
