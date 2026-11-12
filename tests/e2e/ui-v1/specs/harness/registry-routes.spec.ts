/**
 * Self-tests for the registry-driven helpers.
 *
 * The pattern utilities are plain code. The registry checks guard against an
 * empty or mis-shaped registry, which would otherwise generate no tests. Then
 * every page the E2E image renders as v1 (registered pages plus P0-T03's
 * demo pages) gets the redirect check, and every toggle page the old-version
 * round trip, against the live platform.
 */

import {
  REGISTRY,
  type RegistryEntry,
  TOGGLE_PAGES,
} from "../../contract/registry.ts";
import {
  currentDistribution,
  DIST,
  expect,
  test,
} from "../../fixtures/index.ts";
import {
  expectOldVersionRoundTrip,
  expectV0RedirectsToV1,
} from "../../helpers/index.ts";
import { fillPattern, paramNames, routeRegex } from "../../helpers/routes.ts";

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

  test("a final splat fills like the frontend's fillPattern", () => {
    const pattern = "/:orgName/old/*";
    // Slashes kept, each segment encoded.
    expect(fillPattern(pattern, { orgName: "acme", "*": "a b/details" })).toBe(
      "/acme/old/a%20b/details",
    );
    // Omitted: an empty rest, which routeRegex matches with or without "/".
    const bare = fillPattern(pattern, { orgName: "acme" });
    expect(bare).toBe("/acme/old/");
    expect(routeRegex(bare).test("http://x.io/acme/old")).toBe(true);
    // A `*` elsewhere is not a splat.
    expect(fillPattern("/:orgName/a*b", { orgName: "o" })).toBe("/o/a*b");
  });
});

/** Patterns this generic check can fill: only the org segment. */
function orgOnly(patterns: readonly string[]): boolean {
  return patterns.every((p) =>
    paramNames(p).every((name) => name === "orgName"),
  );
}

function mappedPatterns(map: Readonly<Record<string, string>>): string[] {
  return [...Object.keys(map), ...Object.values(map)];
}

const live: readonly RegistryEntry[] = REGISTRY.filter((e) =>
  e.distributions.includes(currentDistribution()),
);

test.describe("harness: registry contents", { tag: DIST.all }, () => {
  test("the E2E image has v1 pages to check, demo pages included", () => {
    // Empty would make the loops below generate nothing and pass.
    expect(live.length).toBeGreaterThan(0);
    expect(live.map((e) => e.page)).toEqual(
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
  for (const entry of live) {
    test(`${entry.page}: v0 URLs redirect to v1`, async ({ page, app }) => {
      test.skip(
        !orgOnly(mappedPatterns(entry.toV1)),
        "routes need ids; the page spec covers them",
      );
      await expectV0RedirectsToV1(page, entry.page, { orgName: app.orgName });
    });

    if (entry.toggle) {
      test(`${entry.page}: old-version round trip`, async ({
        page,
        app,
        session,
      }) => {
        test.skip(
          !orgOnly(mappedPatterns(entry.toV0)),
          "routes need ids; the page spec covers them",
        );
        await expectOldVersionRoundTrip(page, entry.page, {
          params: { orgName: app.orgName },
          userId: session.userId,
        });
      });
    }
  }

  test("the round trip refuses a page without the toggle", async ({ page }) => {
    const plain = live.find((e) => !e.toggle);
    expect(plain, "a non-toggle page to refuse").toBeDefined();
    await expect(
      expectOldVersionRoundTrip(page, plain?.page ?? "DEMO-PAGE", {
        params: {},
        userId: "0",
      }),
    ).rejects.toThrow("Human Review (toggle: true) only");
  });
});
