/**
 * Opens each v0 URL a registered page replaces and asserts it lands on the
 * mapped v1 route, rendered by the v1 tree.
 *
 *   await expectV0RedirectsToV1(page, "UN06", { orgName: app.orgId });
 *
 * Reads the mapping (`toV1`) from contract/registry.ts only. Params fill the
 * `:name` segments of both patterns; a mapping whose pattern needs a param
 * that was not given fails with that name, so pass every param the page uses.
 */

import { expect, type Page, test } from "@playwright/test";
import { findEntry, type PageKey } from "../contract/registry.ts";
import { V1_ROOT_SELECTOR } from "../contract/v1-ui.ts";
import { currentDistribution } from "../fixtures/tags.ts";
import { fillPattern, type RouteParams, routeRegex } from "./routes.ts";

export async function expectV0RedirectsToV1(
  page: Page,
  pageKey: PageKey,
  params: RouteParams,
): Promise<void> {
  const entry = findEntry(pageKey);
  const distribution = currentDistribution();
  if (!entry.distributions.includes(distribution)) {
    throw new Error(`${pageKey} is not registered for ${distribution}`);
  }
  const mappings = Object.entries(entry.toV1);
  if (!mappings.length) {
    throw new Error(`${pageKey} has no v0 -> v1 mappings in the registry`);
  }
  for (const [v0, v1] of mappings) {
    const body = async () => {
      const target = fillPattern(v1, params);
      await page.goto(fillPattern(v0, params), {
        waitUntil: "domcontentloaded",
      });
      await expect(page).toHaveURL(routeRegex(target));
      await expect(page.locator(V1_ROOT_SELECTOR)).toBeVisible();
    };
    await test.step(`redirect ${v0} -> ${v1}`, body); // NOSONAR: steps share one page, so they run in order
  }
}
