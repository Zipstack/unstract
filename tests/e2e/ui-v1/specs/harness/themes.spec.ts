/** Self-test: the theme matrix visits every theme and the hook survives reloads. */

import { THEME_ATTRIBUTE, THEMES, type Theme } from "../../contract/v1-ui.ts";
import { DIST, expect, test } from "../../fixtures/index.ts";
import { forEachTheme } from "../../helpers/index.ts";
import { installDemoPage, openDemoPage } from "../../support/demo-page.ts";

test.describe("harness: theme matrix", { tag: DIST.all }, () => {
  test("runs the check once per theme, with the theme applied", async ({
    page,
  }) => {
    await installDemoPage(page);
    const seen: Theme[] = [];
    const backgrounds = new Set<string>();

    await forEachTheme(page, async (theme) => {
      await openDemoPage(page);
      const html = page.locator("html");
      await expect(html).toHaveAttribute(THEME_ATTRIBUTE, theme);
      await expect(html).toHaveClass(new RegExp(`\\b${theme}\\b`));
      // Navigation happened after the theme was set: the init script held.
      backgrounds.add(
        await page.evaluate(() => getComputedStyle(document.body).background),
      );
      seen.push(theme);
    });

    expect(seen).toEqual([...THEMES]);
    expect(backgrounds.size, "every theme should paint differently").toBe(
      THEMES.length,
    );
  });

  test("a pluggable setTheme replaces the default", async ({ page }) => {
    await installDemoPage(page);
    const calls: Theme[] = [];
    await forEachTheme(page, async () => {}, {
      themes: ["dark"],
      setTheme: async (_page, theme) => {
        calls.push(theme);
      },
    });
    expect(calls).toEqual(["dark"]);
  });
});
