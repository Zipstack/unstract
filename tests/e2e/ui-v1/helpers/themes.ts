/**
 * Repeats a check in Light, Dark and Unstract on a v1 page.
 *
 *   await forEachTheme(page, async (theme) => {
 *     await app.goto("workflows");
 *     await expectAccessible(page, { label: theme });
 *   });
 *
 * `defaultSetTheme` stores the mode where the v1 theme store reads it
 * (localStorage `unstract.v1.theme`, P0-T04). The store hydrates when the v1
 * tree mounts, so the check must open (or reload) the page after it. After
 * each check, the v1 root must carry the theme: a hook that did not take
 * fails here instead of scanning one theme three times.
 */

import { expect, type Page, test } from "@playwright/test";
import {
  THEME_ATTRIBUTE,
  THEME_STORAGE_KEY,
  THEMES,
  type Theme,
  V1_ROOT_SELECTOR,
} from "../contract/v1-ui.ts";

export type SetTheme = (page: Page, theme: Theme) => Promise<void>;

function storeTheme([key, theme]: [string, Theme]): void {
  // Serialised into the page, so it must not reference anything outside.
  try {
    localStorage.setItem(key, theme);
  } catch {
    // about:blank and opaque origins have no storage; the init script retries.
  }
}

/**
 * The theme init script live on each page. Playwright leaves the order of
 * several init scripts undefined, so there is only ever one: the previous
 * theme's is disposed before the next is added.
 */
type InitScript = Awaited<ReturnType<Page["addInitScript"]>>;
const themeScripts = new WeakMap<Page, InitScript>();

export const defaultSetTheme: SetTheme = async (page, theme) => {
  const args: [string, Theme] = [THEME_STORAGE_KEY, theme];
  await themeScripts.get(page)?.dispose();
  themeScripts.set(page, await page.addInitScript(storeTheme, args));
  if (page.url() !== "about:blank") {
    await page.evaluate(storeTheme, args);
  }
};

export interface ThemeOptions {
  themes?: readonly Theme[];
  setTheme?: SetTheme;
}

export async function forEachTheme(
  page: Page,
  check: (theme: Theme) => Promise<void>,
  { themes = THEMES, setTheme = defaultSetTheme }: ThemeOptions = {},
): Promise<void> {
  if (!themes.length) {
    // An empty list would pass having checked nothing.
    throw new Error("forEachTheme: `themes` is empty");
  }
  for (const theme of themes) {
    const body = async () => {
      await setTheme(page, theme);
      await check(theme);
      await expect(
        page.locator(V1_ROOT_SELECTOR).first(),
        `the v1 root did not render in "${theme}"; did the check open a v1 page after the theme was set?`,
      ).toHaveAttribute(THEME_ATTRIBUTE, theme);
    };
    await test.step(`theme: ${theme}`, body); // NOSONAR: steps share one page, so they run in order
  }
}
