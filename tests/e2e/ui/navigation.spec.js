import { expect, test } from "./fixtures.js";

/**
 * Navigation — the sidebar is how every other page is reached.
 *
 * Not a critical path in its own right, but a break here blocks all of them, so
 * it earns a place in a deliberately small suite. One test walks the primary
 * destinations; the second covers the Platform fly-out, which is the only route
 * to the settings screens.
 */

/** Primary destinations, and a landmark that proves each one actually rendered. */
const DESTINATIONS = [
  { menu: "Prompt Studio", route: "tools", landmark: /New Project/i },
  { menu: "Workflows", route: "workflows", landmark: /New Workflow/i },
  { menu: "API Deployments", route: "api", landmark: /API Deployment/i },
  // "ETL Executions" is a Logs-only tab; a bare /Logs/ would also match the
  // Logs footer panel, which is present on every page.
  { menu: "Logs", route: "logs", landmark: /ETL Executions/i },
];

test.describe("navigation", () => {
  for (const { menu, route, landmark } of DESTINATIONS) {
    test(`the sidebar reaches ${menu}`, async ({ page, app }) => {
      // Start somewhere else so the click has to actually navigate.
      await app.goto("workflows");

      const item = page.locator(
        `[data-testid='sidebar-${menu.toLowerCase().replaceAll(/\s+/g, "-")}']`,
      );
      if ((await item.count()) === 0) {
        test.skip(true, `${menu} not present for this user/plan`);
      }
      await item.scrollIntoViewIfNeeded();
      await item.click();

      await expect(page, `${menu} did not navigate`).toHaveURL(
        new RegExp(`/${route}(/|$|\\?)`),
        { timeout: 20000 },
      );
      await expect(
        page.getByText(landmark).first(),
        `${menu} navigated but did not render`,
      ).toBeVisible({ timeout: 20000 });
    });
  }

  /*
   * The settings screens have no top-level sidebar entry — the Platform
   * fly-out is the only way in, so a user locked out of it cannot configure
   * adapters, users or platform keys at all.
   */
  test("the Platform fly-out reaches the settings screens", async ({
    page,
    app,
  }) => {
    await app.goto("tools");

    const item = page.locator("[data-testid='sidebar-platform']");
    if ((await item.count()) === 0) {
      test.skip(true, "Platform menu not present for this user");
    }
    await item.scrollIntoViewIfNeeded();
    await item.hover();

    /*
     * Was `.settings-sidebar-popover`, which the HITL fly-out ALSO uses — so
     * the locator was ambiguous the moment both were rendered. Each panel now
     * has its own id, and its entries derive theirs from the menu item keys.
     */
    const menu = page.getByTestId("platform-menu");
    await expect(menu, "Platform fly-out did not open").toBeVisible({
      timeout: 10000,
    });

    await menu.getByTestId("platform-menu-item-users").click();
    await expect(page).toHaveURL(/\/users(\/|$|\?)/, { timeout: 20000 });
    await expect(page.getByText(/Manage Users/i).first()).toBeVisible();
  });
});
