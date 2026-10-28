/**
 * Self-tests for the org the session hands to specs: API calls use its id,
 * browser routes its name, and the two differ on cloud (`org_…` vs a slug).
 */

import { routedOrganization } from "../../fixtures/auth.ts";
import { DIST, expect, test } from "../../fixtures/index.ts";

const LISTED = { id: "org_2xKq9", name: "acme-listed" };

test.describe("harness: organisation id vs name", { tag: DIST.all }, () => {
  test("routes by the name the set response carries", () => {
    expect(
      routedOrganization(LISTED, { organization: { name: "acme" } }),
    ).toEqual({ id: "org_2xKq9", name: "acme" });
  });

  test("falls back to the listed name", () => {
    for (const body of [null, {}, { organization: { name: "" } }]) {
      expect(routedOrganization(LISTED, body)).toEqual(LISTED);
    }
  });

  test.describe("app.goto", () => {
    // A stand-in session: no stack needed to see which segment goto uses.
    test.use({
      session: async ({ context }, use) => {
        await use({
          role: "admin",
          mode: "oss",
          orgId: "org_2xKq9",
          orgName: "acme",
          api: context.request,
          csrfHeaders: async () => ({}),
        });
      },
    });

    test("opens /<orgName>/<route>, never the id", async ({ page, app }) => {
      const opened: string[] = [];
      await page.route("**/*", (route) => {
        opened.push(new URL(route.request().url()).pathname);
        return route.fulfill({
          contentType: "text/html",
          body: "<html></html>",
        });
      });
      await app.goto("workflows");
      expect(opened[0]).toBe("/acme/workflows");
      expect(app.orgId).toBe("org_2xKq9");
    });
  });
});
