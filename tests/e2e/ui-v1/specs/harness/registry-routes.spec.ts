/**
 * Self-tests for the registry-driven helpers.
 *
 * The pattern utilities are plain code. The registry checks guard against an
 * empty or mis-shaped registry, which would otherwise generate no tests. Then
 * every page the E2E image renders as v1 (registered pages plus P0-T03's
 * demo pages) gets the redirect check, and every toggle page the old-version
 * round trip, against the live platform.
 */

import { REGISTRY, TOGGLE_PAGES } from "../../contract/registry.ts";
import { DIST, expect, test } from "../../fixtures/index.ts";
import {
  expectOldVersionRoundTrip,
  expectV0RedirectsToV1,
} from "../../helpers/index.ts";
import {
  fillable,
  fillPattern,
  paramNames,
  type RouteParams,
  routeRegex,
} from "../../helpers/routes.ts";

test.describe("harness: route patterns", { tag: DIST.all }, () => {
  test("fills params and matches the filled URL", () => {
    const pattern = "/:orgName/workflows/:id";
    expect(paramNames(pattern)).toEqual(["orgName", "id"]);
    const path = fillPattern(pattern, { orgName: "org_1", id: "a b" });
    expect(path).toBe("/org_1/workflows/a%20b");

    const re = routeRegex(path);
    expect(re.test("http://localhost:3000/org_1/workflows/a%20b")).toBe(true);
    expect(re.test("http://x.io/org_1/workflows/a%20b/?tab=2")).toBe(true);
    expect(re.test("http://x.io/org_1/workflows/a%20b/extra")).toBe(false);
  });

  test("a missing param names itself", () => {
    expect(() => fillPattern("/:orgName/x/:id", { orgName: "o" })).toThrow(
      ":id",
    );
  });

  test("a final splat fills as the frontend's fillPattern does", () => {
    const pattern = "/:orgName/old/*";
    // Slashes kept, each segment encoded.
    expect(fillPattern(pattern, { orgName: "acme", "*": "a b/details" })).toBe(
      "/acme/old/a%20b/details",
    );
    // Omitted: no rest and no trailing slash (generatePath gives the same).
    expect(fillPattern(pattern, { orgName: "acme" })).toBe("/acme/old");
    // paramNames is the frontend's own, splat included.
    expect(paramNames(pattern)).toEqual(["orgName", "*"]);
  });
});

/**
 * The generic checks fill only the org. A page's mappings that need more
 * (ids) are left to its own spec, and when none can be filled the test skips
 * naming the params, so the gap shows in the report.
 */
function orgFillable(params: RouteParams) {
  return (from: string, to: string) =>
    fillable(from, params) && fillable(to, params);
}

function missingParams(
  map: Readonly<Record<string, string>>,
  params: RouteParams,
): string[] {
  const names = Object.entries(map).flatMap(([from, to]) => [
    ...paramNames(from),
    ...paramNames(to),
  ]);
  return [...new Set(names)].filter(
    (name) => name !== "*" && params[name] === undefined,
  );
}

function skipUnlessFillable(
  map: Readonly<Record<string, string>>,
  params: RouteParams,
): void {
  const only = orgFillable(params);
  test.skip(
    !Object.entries(map).some(([from, to]) => only(from, to)),
    `every mapping needs ${missingParams(map, params).join(", ")}; the page's own spec must check it with those params`,
  );
}

test.describe("harness: registry contents", { tag: DIST.all }, () => {
  test("the E2E image has v1 pages to check, demo pages included", () => {
    // Empty would make the loops below generate nothing and pass.
    expect(REGISTRY.length).toBeGreaterThan(0);
    expect(REGISTRY.map((e) => e.page)).toEqual(
      expect.arrayContaining(["DEMO-PAGE", "DEMO-REVIEW"]),
    );
  });

  test("exactly the toggle pages honour the old-version preference (D14)", () => {
    const toggles = REGISTRY.filter((e) => e.toggle).map((e) => e.page);
    const allowed = TOGGLE_PAGES.filter((key) =>
      REGISTRY.some((e) => e.page === key),
    );
    expect(toggles.length).toBeGreaterThan(0);
    expect([...toggles].sort()).toEqual([...allowed].sort());
  });
});

test.describe("harness: registry-driven checks", { tag: DIST.all }, () => {
  for (const entry of REGISTRY) {
    test(`${entry.page}: v0 URLs redirect to v1`, async ({ page, app }) => {
      const params = { orgName: app.orgName };
      skipUnlessFillable(entry.toV1, params);
      await expectV0RedirectsToV1(page, entry.page, params, {
        only: orgFillable(params),
      });
    });

    if (entry.toggle) {
      test(`${entry.page}: old-version round trip`, async ({
        page,
        app,
        session,
      }) => {
        const params = { orgName: app.orgName };
        skipUnlessFillable(entry.toV0, params);
        await expectOldVersionRoundTrip(page, entry.page, {
          params,
          userId: session.userId,
          only: orgFillable(params),
        });
      });
    }
  }

  test("the round trip refuses a page without the toggle", async ({ page }) => {
    const plain = REGISTRY.find((e) => !e.toggle);
    expect(plain, "a non-toggle page to refuse").toBeDefined();
    await expect(
      expectOldVersionRoundTrip(page, plain?.page ?? "DEMO-PAGE", {
        params: {},
        userId: "0",
      }),
    ).rejects.toThrow("for toggle pages");
  });
});
