import { expect, test } from "./fixtures.js";

/**
 * Left sidebar fly-outs (Platform, HITL).
 *
 * Three regressions here, none of them observable without layout: the fly-out
 * rendered off-screen, it was clipped by the Logs footer, and its first entry
 * always looked selected.
 */
test.describe("sidebar fly-outs", () => {
  /*
   * Radix identifies an `asChild` trigger by the ref passed down. The Tooltip
   * nested between the Popover and its trigger forwarded handlers but dropped
   * the ref, leaving the Popover with no anchor: Platform's 236x308 panel was
   * positioned at y=-616, entirely above the viewport. It WAS open and
   * correctly populated — which is why only a geometry assertion catches it.
   */
  test("the Platform fly-out opens inside the viewport", async ({
    page,
    app,
  }) => {
    await app.goto("tools");
    const item = page.locator("[data-testid='sidebar-platform']");
    if ((await item.count()) === 0) {
      test.skip(true, "platform sidebar item not present");
    }
    await item.scrollIntoViewIfNeeded();
    await item.hover();

    const panel = page.locator("[data-radix-popper-content-wrapper]").first();
    await expect(panel).toBeVisible({ timeout: 5000 });

    const box = await panel.boundingBox();
    expect(box, "fly-out has no box").not.toBeNull();
    expect(box.y, "fly-out is positioned above the viewport").toBeGreaterThan(-1);
    const viewport = page.viewportSize();
    expect(box.y, "fly-out starts below the viewport").toBeLessThan(viewport.height);
  });

  /*
   * `.logs-container` is z-index 999; Radix positions overlays at 50. A fly-out
   * opened near the bottom of the screen was drawn UNDER the Logs footer.
   */
  test("the fly-out paints above the Logs footer", async ({ page, app }) => {
    await app.goto("tools");
    const item = page.locator("[data-testid='sidebar-platform']");
    if ((await item.count()) === 0) {
      test.skip(true, "platform sidebar item not present");
    }
    await item.scrollIntoViewIfNeeded();
    await item.hover();

    const panel = page.locator("[data-radix-popper-content-wrapper]").first();
    await expect(panel).toBeVisible({ timeout: 5000 });

    const stacking = await page.evaluate(() => {
      const p = document.querySelector("[data-radix-popper-content-wrapper]");
      const logs = document.querySelector(".logs-container");
      if (!p || !logs) return null;
      return {
        panel: Number.parseInt(getComputedStyle(p).zIndex, 10) || 0,
        logs: Number.parseInt(getComputedStyle(logs).zIndex, 10) || 0,
      };
    });
    if (stacking === null) {
      test.skip(true, "logs footer not rendered");
    }
    expect(
      stacking.panel,
      "fly-out sits below the Logs footer and gets clipped",
    ).toBeGreaterThan(stacking.logs);
  });

  /*
   * `getActiveHITLKey` fell through to its FIRST entry when the route was not
   * under HITL at all, so "Review" looked selected from everywhere in the app.
   */
  test("no fly-out entry looks selected from an unrelated page", async ({
    page,
    app,
  }) => {
    await app.goto("tools");
    const item = page.locator("[data-testid='sidebar-hitl']");
    if ((await item.count()) === 0) {
      test.skip(true, "HITL sidebar item not present");
    }
    await item.scrollIntoViewIfNeeded();
    await item.hover();

    const menu = page.locator(".settings-sidebar-popover");
    await expect(menu).toBeVisible({ timeout: 5000 });
    await expect(
      menu.locator(".settings-menu-item.active"),
      "an entry is marked active on a page outside that section",
    ).toHaveCount(0);
  });
});
