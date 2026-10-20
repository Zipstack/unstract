/**
 * Self-tests for the P0-T03-dependent helpers.
 *
 * The pattern utilities are plain code and run now. The redirect and
 * old-version checks run once per registered page, so with the stub registry
 * they skip with the reason; they turn on by themselves when
 * contract/registry.ts points at the real registry.
 */

import {
  REGISTRY,
  REGISTRY_PENDING_REASON,
  registryAvailable,
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
});

/** Patterns this generic check can fill: only the org segment. */
function orgOnly(patterns: readonly string[]): boolean {
  return patterns.every((p) =>
    paramNames(p).every((name) => name === "orgName"),
  );
}

const registered = REGISTRY.filter((e) =>
  e.distributions.includes(currentDistribution()),
);

test.describe("harness: registry-driven checks", { tag: DIST.all }, () => {
  test.skip(!registryAvailable(), REGISTRY_PENDING_REASON);

  test("only Human Review honours the old-version preference (D14)", () => {
    const toggles = REGISTRY.filter((e) => e.toggle).map((e) => e.page);
    expect(toggles.every((p) => p === "UN11")).toBe(true);
  });

  for (const entry of registered) {
    const filled = orgOnly([
      ...Object.keys(entry.toV1),
      ...Object.values(entry.toV1),
    ]);

    test(`${entry.page}: v0 URLs redirect to v1`, async ({ page, app }) => {
      test.skip(!filled, "routes need ids; the page spec covers them");
      await expectV0RedirectsToV1(page, entry.page, { orgName: app.orgId });
    });

    if (entry.toggle) {
      test(`${entry.page}: old-version round trip`, async ({ page, app }) => {
        test.skip(
          !orgOnly([...Object.keys(entry.toV0), ...Object.values(entry.toV0)]),
          "routes need ids; the page spec covers them",
        );
        await expectOldVersionRoundTrip(page, entry.page, {
          orgName: app.orgId,
        });
      });
    }
  }
});
