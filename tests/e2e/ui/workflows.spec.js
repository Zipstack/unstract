import {
  expect,
  expectNoHorizontalOverflow,
  test,
} from "./fixtures.js";

/**
 * Workflows listing and detail.
 *
 * Guards the horizontal-scrollbar regression: shadcn's Alert base is `w-full`
 * where antd's sized to its container, so `.deployment-alert`'s `margin: 0
 * 24px` made the box 100% + 48px and `.agency-layout` (overflow-x: auto) grew a
 * scrollbar on every workflow that has a deployment.
 */
test.describe("workflows", () => {
  test("the listing renders without horizontal overflow", async ({
    page,
    app,
  }) => {
    await app.goto("workflows");
    await expect(page.getByText("Workflows").first()).toBeVisible();
    await expectNoHorizontalOverflow(page, "workflows listing");
  });

  test("a workflow detail page does not scroll horizontally", async ({
    page,
    app,
  }) => {
    await app.goto("workflows");

    // Open the first workflow if the org has one; otherwise there is nothing
    // to assert and the regression cannot manifest.
    const card = page.locator(".card-list-content, [class*='workflow']").first();
    if ((await card.count()) === 0) {
      test.skip(true, "no workflows in this org");
    }
    await card.click();
    await page.waitForLoadState("networkidle").catch(() => {});

    await expectNoHorizontalOverflow(page, "workflow detail");

    // The specific element that overflowed: its box plus margins must fit the
    // scroll container, not exceed it by the margin width.
    const alert = page.locator(".deployment-alert");
    if ((await alert.count()) > 0) {
      const fits = await alert.evaluate((el) => {
        const layout = el.closest(".agency-layout");
        return !layout || layout.scrollWidth <= layout.clientWidth;
      });
      expect(fits, ".deployment-alert overflows .agency-layout").toBe(true);
    }
  });
});
