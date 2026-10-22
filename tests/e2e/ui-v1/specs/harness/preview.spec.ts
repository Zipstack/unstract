/**
 * Self-test: `v1Preview` makes an unregistered page render as v1. Skips until
 * P0-T03 provides the dev/test override (contract/registry.ts V1_PREVIEW).
 */

import {
  PREVIEW_PENDING_REASON,
  REGISTRY,
  V1_PREVIEW,
} from "../../contract/registry.ts";
import { V1_ROOT_SELECTOR } from "../../contract/v1-ui.ts";
import { DIST, expect, test } from "../../fixtures/index.ts";

test.describe(
  "harness: v1 preview of an unregistered page",
  {
    tag: DIST.all,
  },
  () => {
    test.skip(!V1_PREVIEW, PREVIEW_PENDING_REASON);
    /*
     * P0-T03's dev-only demo page, previewed rather than registered. Set its
     * key and route here when P0-T03 lands.
     */
    const DEMO_KEY = "UN00";
    const DEMO_ROUTE = "v1-demo";
    test.use({ v1Preview: [DEMO_KEY] });

    test("the preview override renders the page's v1 route", async ({
      page,
      app,
    }) => {
      expect(REGISTRY.some((e) => e.page === DEMO_KEY)).toBe(false);
      await app.goto(DEMO_ROUTE);
      await expect(page.locator(V1_ROOT_SELECTOR)).toBeVisible();
    });
  },
);
