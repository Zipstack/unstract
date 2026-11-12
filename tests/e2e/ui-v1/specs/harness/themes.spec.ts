/**
 * Self-test: the theme matrix themes a real v1 page (P0-T03's demo page, so
 * it needs the platform), and a hook that does not take fails instead of
 * checking one theme three times.
 */

import {
  THEME_ATTRIBUTE,
  THEME_STORAGE_KEY,
  THEMES,
  type Theme,
  V1_ROOT_SELECTOR,
} from "../../contract/v1-ui.ts";
import { DIST, expect, test } from "../../fixtures/index.ts";
import { forEachTheme } from "../../helpers/index.ts";
import {
  installStateFixture,
  openStateFixture,
} from "../../support/state-fixture.ts";

const DEMO_ROUTE = "v1-demo";
const DEMO_TEST_ID = "v1-demo";

test.describe("harness: theme matrix", { tag: DIST.all }, () => {
  test("the default hook renders a real v1 page in every theme", async ({
    page,
    app,
  }) => {
    const seen: Theme[] = [];
    const painted = new Set<string>();

    await forEachTheme(page, async (theme) => {
      await app.goto(DEMO_ROUTE);
      await expect(page.getByTestId(DEMO_TEST_ID)).toBeVisible();
      // The v1 CSS keys on the root's data-theme: the paint must change too.
      painted.add(
        await page
          .locator(V1_ROOT_SELECTOR)
          .first()
          .evaluate((root) => {
            const style = getComputedStyle(root);
            return `${style.backgroundColor}|${style.color}`;
          }),
      );
      seen.push(theme);
    });

    expect(seen).toEqual([...THEMES]);
    expect(painted.size, "every theme should paint differently").toBe(
      THEMES.length,
    );
  });

  test("a hook that does not take fails", async ({ page, app }) => {
    const error: unknown = await forEachTheme(
      page,
      async () => {
        await app.goto(DEMO_ROUTE);
      },
      { themes: ["dark"], setTheme: async () => {} },
    ).then(
      () => null,
      (e: unknown) => e,
    );
    expect(String(error)).toContain('did not render in "dark"');
  });

  test("an empty theme list is refused, not passed", async ({ page }) => {
    await expect(
      forEachTheme(page, async () => {}, { themes: [] }),
    ).rejects.toThrow("`themes` is empty");
  });

  test("a pluggable setTheme replaces the default", async ({ page }) => {
    await installStateFixture(page);
    const calls: Theme[] = [];
    await forEachTheme(page, () => openStateFixture(page), {
      themes: ["dark"],
      setTheme: async (p, theme) => {
        calls.push(theme);
        const args: [string, string, string] = [
          V1_ROOT_SELECTOR,
          THEME_ATTRIBUTE,
          theme,
        ];
        await p.addInitScript(([selector, attribute, value]) => {
          document.addEventListener("DOMContentLoaded", () => {
            document.querySelector(selector)?.setAttribute(attribute, value);
          });
        }, args);
      },
    });
    expect(calls).toEqual(["dark"]);
    // The default hook never ran: nothing stored where the app reads it.
    expect(
      await page.evaluate(
        (key) => localStorage.getItem(key),
        THEME_STORAGE_KEY,
      ),
    ).toBeNull();
  });
});
