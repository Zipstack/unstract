import { expect, test } from "@playwright/test";

/**
 * Scaffolding smoke test for the `ui` rig group.
 *
 * Deliberately minimal: it proves the harness works end to end — config
 * resolves, a browser launches, the app is reachable, and JUnit lands where the
 * rig expects it — without asserting anything about a specific screen. Real UI
 * assertions go in sibling spec files.
 *
 * It skips rather than fails when nothing is serving, so `python -m tests.rig
 * run ui` on a machine with no platform reports "skipped", not a red build.
 * The group is `optional` in groups.yaml for the same reason.
 */
test.describe("ui harness", () => {
  test("the app serves a document", async ({ page, baseURL }) => {
    let response;
    try {
      response = await page.goto("/", { waitUntil: "domcontentloaded" });
    } catch (err) {
      test.skip(true, `no app reachable at ${baseURL}: ${err.message}`);
      return;
    }

    // A redirect to the login page is a perfectly good "it's alive" — assert
    // reachability, not a particular route.
    expect(response?.status(), `unexpected status from ${baseURL}`).toBeLessThan(
      400,
    );
    await expect(page).toHaveTitle(/.+/);
  });

  /*
   * The reason this tier exists. jsdom reports every element as 0x0, so a
   * layout assertion like this one is impossible in the Vitest suite — and
   * layout is exactly where the migration regressions landed.
   */
  test("the document does not scroll horizontally", async ({
    page,
    baseURL,
  }) => {
    try {
      await page.goto("/", { waitUntil: "domcontentloaded" });
    } catch (err) {
      test.skip(true, `no app reachable at ${baseURL}: ${err.message}`);
      return;
    }

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow, "page overflows its viewport horizontally").toBeLessThanOrEqual(
      0,
    );
  });
});
