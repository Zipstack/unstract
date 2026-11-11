/**
 * Self-test: `v1Preview` makes a declared, unregistered page render as v1
 * (P0-T03's localStorage override, honoured by the E2E image).
 *
 * The value check runs always. The render check runs once per page declared
 * in the frontend's PAGES but not yet in REGISTERED_PAGES; while there is
 * none, it skips saying so, and turns on by itself when the first page
 * task declares its page.
 */

import {
  isPageKey,
  type PageKey,
  UNREGISTERED_PAGES,
  V1_PREVIEW,
} from "../../contract/registry.ts";
import { V1_ROOT_SELECTOR } from "../../contract/v1-ui.ts";
import { DIST, expect, test } from "../../fixtures/index.ts";
import { previewValue } from "../../fixtures/preview.ts";
import { fillPattern, paramNames } from "../../helpers/routes.ts";

test.describe("harness: v1 preview value", { tag: DIST.all }, () => {
  test("storage holds the JSON array of page keys the app parses", () => {
    const pages: PageKey[] = ["UN13", "UN14"];
    const parsed: unknown = JSON.parse(previewValue(V1_PREVIEW, pages));
    expect(parsed).toEqual(pages);
    // readPreviewPages drops anything that is not a valid page key.
    expect((parsed as unknown[]).every(isPageKey)).toBe(true);
  });

  test("a cookie holds a URI-encoded value", () => {
    const pages: PageKey[] = ["UN13", "UN14"];
    const cookie = previewValue({ kind: "cookie", name: "v1" }, pages);
    // RFC 6265 cookie-octets exclude DQUOTE, comma, semicolon and backslash.
    expect(cookie).not.toMatch(/[",;\\\s]/);
    expect(JSON.parse(decodeURIComponent(cookie))).toEqual(pages);
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
        test.skip(
          true,
          "no page is declared in PAGES and unregistered yet; runs once the first page task declares one",
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
          test.skip(!route, "routes need ids; the page spec covers them");
          await page.goto(fillPattern(route ?? "", { orgName: app.orgName }));
          await expect(page.locator(V1_ROOT_SELECTOR)).toBeVisible();
        });
      });
    }
  },
);
