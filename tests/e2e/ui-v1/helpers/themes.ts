/**
 * Repeats a check in Light, Dark and Unstract.
 *
 *   await forEachTheme(page, async (theme) => {
 *     await app.goto("workflows");
 *     await expectAccessible(page, { label: theme });
 *   });
 *
 * How a theme is applied belongs to P0-T04, which has not landed. Until then
 * `defaultSetTheme` stands in: it sets `data-theme` and a same-named class on
 * <html>, now and on every later navigation. Pass `setTheme` to use another
 * mechanism, and switch the default here once P0-T04 publishes its own.
 */

import { type Page, test } from "@playwright/test";
import { THEME_ATTRIBUTE, THEMES, type Theme } from "../contract/v1-ui.ts";

export type SetTheme = (page: Page, theme: Theme) => Promise<void>;

function applyTheme([attribute, theme, all]: [
  string,
  Theme,
  readonly Theme[],
]): void {
  // Serialised into the page, so it must not reference anything outside.
  const apply = () => {
    const root = document.documentElement;
    root.setAttribute(attribute, theme);
    root.classList.remove(...all);
    root.classList.add(theme);
  };
  // As an init script this runs before the parser creates <html>.
  if (document.documentElement) {
    apply();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", apply);
  }
}

export const defaultSetTheme: SetTheme = async (page, theme) => {
  const args: [string, Theme, readonly Theme[]] = [
    THEME_ATTRIBUTE,
    theme,
    THEMES,
  ];
  // Init scripts run in the order added, so the latest theme wins on reload.
  await page.addInitScript(applyTheme, args);
  await page.evaluate(applyTheme, args);
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
  for (const theme of themes) {
    await test.step(`theme: ${theme}`, async () => {
      await setTheme(page, theme);
      await check(theme);
    });
  }
}
