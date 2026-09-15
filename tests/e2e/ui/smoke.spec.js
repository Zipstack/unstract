import { expect, test } from "@playwright/test";

/**
 * Scaffolding smoke test for the `ui` rig group.
 *
 * Deliberately minimal: it proves the harness works end to end — config
 * resolves, a browser launches, the app is reachable, and JUnit lands where the
 * rig expects it — without asserting anything about a specific screen. Real UI
 * assertions go in sibling spec files.
 *
 * It skips rather than fails when nothing is serving, so running the specs
 * directly on a machine with no platform reports "skipped", not a red build.
 * The group is `optional` in groups.yaml for the same reason.
 *
 * That skip is gated on UNSTRACT_RIG_SESSION_ID, which `tests/rig/cli.py` sets
 * unconditionally for every group that declares `requires_platform`. When it
 * is present the rig booted the stack and `_wait_ready` already proved the
 * frontend answers, so an unreachable app is a REAL failure — swallowing it
 * there let the whole group report success without ever opening the UI.
 */
const RIG_MANAGED = Boolean(process.env.UNSTRACT_RIG_SESSION_ID);

test.describe("ui harness", () => {
  test("the app serves a document", async ({ page, baseURL }) => {
    let response;
    try {
      response = await page.goto("/", { waitUntil: "domcontentloaded" });
    } catch (err) {
      if (RIG_MANAGED) {
        throw new Error(
          `the rig reported the platform up, but nothing is serving at ` +
            `${baseURL}: ${err.message}`,
        );
      }
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
});
