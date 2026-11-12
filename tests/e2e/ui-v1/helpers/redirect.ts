/**
 * Opens each v0 URL a registered page replaces and asserts it lands on the
 * mapped v1 route, rendered by the v1 tree.
 *
 *   await expectV0RedirectsToV1(page, "UN06", { orgName: app.orgName });
 *
 * Reads the mapping (`toV1`) from contract/registry.ts only. Params fill the
 * `:name` segments of both patterns; a mapping whose pattern needs a param
 * that was not given fails with that name, so pass every param the page uses.
 * `only` narrows the check to some mappings; the ones it leaves must not be
 * empty.
 */

import { expect, type Page, test } from "@playwright/test";
import { currentDistribution } from "../contract/distribution.ts";
import { findEntry, type PageKey, shipsIn } from "../contract/registry.ts";
import { V1_ROOT_SELECTOR } from "../contract/v1-ui.ts";
import { fillPattern, type RouteParams, routeRegex } from "./routes.ts";

export type MappingFilter = (from: string, to: string) => boolean;

export async function expectV0RedirectsToV1(
  page: Page,
  pageKey: PageKey,
  params: RouteParams,
  { only = () => true }: { only?: MappingFilter } = {},
): Promise<void> {
  const entry = findEntry(pageKey);
  const distribution = currentDistribution();
  if (!shipsIn(entry, distribution)) {
    throw new Error(`${pageKey} is not registered for ${distribution}`);
  }
  const mappings = Object.entries(entry.toV1).filter(([v0, v1]) =>
    only(v0, v1),
  );
  if (!mappings.length) {
    throw new Error(`${pageKey} has no v0 -> v1 mappings to check`);
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
