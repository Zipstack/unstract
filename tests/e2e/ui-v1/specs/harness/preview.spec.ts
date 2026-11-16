/**
 * Self-test: `v1Preview` makes a declared, unregistered page render as v1
 * (P0-T03's localStorage override, honoured by the E2E image).
 *
 * The value check runs always. The render check runs once per page declared
 * in the frontend's PAGES, not yet in REGISTERED_PAGES and shipped in this
 * run's distribution; while there is none, it skips saying so, and turns on
 * by itself when the first page task declares its page.
 */

import {
  PAGES,
  REGISTERED_PAGES,
} from "../../../../../frontend/src/v1/app/registry/entries.ts";
import { currentDistribution } from "../../contract/distribution.ts";
import {
  findEntry,
  isPageKey,
  type PageKey,
  shipsIn,
  UNREGISTERED_PAGES,
} from "../../contract/registry.ts";
import { V1_ROOT_SELECTOR } from "../../contract/v1-ui.ts";
import { DIST, expect, test } from "../../fixtures/index.ts";
import { assertPreviewable, previewValue } from "../../fixtures/preview.ts";
import { fillPattern, paramNames } from "../../helpers/routes.ts";

/** Every key the registry's format allows (validate.ts's PAGE_KEY), DEMO-… aside. */
const TARGET_KEYS: PageKey[] = [
  ...Array.from(
    { length: 20 },
    (_, i) => `UN${String(i + 1).padStart(2, "0")}`,
  ),
  ...Array.from({ length: 7 }, (_, i) => `LW0${i + 1}`),
] as PageKey[];

/** A valid page key no page has declared yet, chosen at run time. */
function undeclaredKey(): PageKey | undefined {
  return TARGET_KEYS.find((key) => {
    try {
      findEntry(key);
      return false;
    } catch {
      return true;
    }
  });
}

test.describe("harness: v1 preview value", { tag: DIST.all }, () => {
  test("storage holds the JSON array of page keys the app parses", () => {
    const pages: PageKey[] = ["UN13", "UN14"];
    const parsed: unknown = JSON.parse(previewValue(pages));
    expect(parsed).toEqual(pages);
    // readPreviewPages drops anything that is not a valid page key.
    expect((parsed as unknown[]).every(isPageKey)).toBe(true);
  });

  test("v1Preview refuses a page the app could not render here", () => {
    // Declared and shipped everywhere: accepted.
    expect(() => assertPreviewable(["DEMO-PAGE"])).not.toThrow();
    // A valid key nobody has declared: the app has no routes for it.
    const key = undeclaredKey();
    test.skip(!key, "every target page is declared");
    expect(() => assertPreviewable([key as PageKey])).toThrow("not declared");
  });
});

/** The first v1 route the check can open with only the org filled in. */
function openableRoute(routes: readonly string[]): string | undefined {
  return routes.find((r) => paramNames(r).every((name) => name === "orgName"));
}

test.describe(
  "harness: v1 preview of an unregistered page",
  { tag: DIST.all },
  () => {
    if (!UNREGISTERED_PAGES.length) {
      // A visible skip, not an empty describe that reports nothing.
      test("the preview override renders an unregistered page", () => {
        // Checks the contract's derivation against the frontend's raw data,
        // so a wrong UNREGISTERED_PAGES cannot hide a page behind this skip.
        const expected = PAGES.filter(
          (e) =>
            !REGISTERED_PAGES.includes(e.page) &&
            shipsIn(e, currentDistribution()),
        );
        expect(UNREGISTERED_PAGES).toEqual(expected);
        test.skip(
          true,
          `no page is declared in PAGES, unregistered and shipped in ${currentDistribution()} yet; runs once a page task declares one`,
        );
      });
    }

    for (const entry of UNREGISTERED_PAGES) {
      test.describe(entry.page, () => {
        test.use({ v1Preview: [entry.page] });

        test("the preview override renders its v1 route", async ({
          page,
          app,
        }) => {
          const route = openableRoute(entry.v1Routes);
          test.skip(
            !route,
            `every v1 route needs more than the org (${entry.v1Routes.join(", ")}); the page's own spec must preview it with those params`,
          );
          await page.goto(fillPattern(route ?? "", { orgName: app.orgName }));
          await expect(page.locator(V1_ROOT_SELECTOR)).toBeVisible();
        });
      });
    }
  },
);
