/**
 * DOM markers and storage keys the helpers rely on, in one place. The theme
 * values come from the frontend's own module, so they cannot drift.
 */

export {
  THEME_MODES as THEMES,
  THEME_STORAGE_KEY,
  type ThemeMode as Theme,
} from "../../../../frontend/src/v1/lib/theme.ts";

/** The v1 tree root (ThemeProvider), which tells v1 apart from v0. */
export const V1_ROOT_SELECTOR = '[data-ui-version="v1"]';

/** The v1 root carries the rendered theme in this attribute. */
export const THEME_ATTRIBUTE = "data-theme";

/**
 * Anything visible inside the SPA mount (frontend/index.html `#root`). "No v1
 * root" only means v0 rendered once this exists; before React mounts, the
 * page has no v1 root either. Not `#root > *`: v0 puts a script and hidden
 * wrappers there first. `:visible` is Playwright's pseudo-class.
 */
export const APP_MOUNTED_SELECTOR = "#root *:visible";

/**
 * Test ids of the one skeleton, empty state, error and no-permission view.
 * Still assumed: the core state components (P1) define the real ids, and the
 * selector convention for v1 tests is pending a team decision.
 */
export const STATE_TEST_IDS = {
  loading: "v1-state-loading",
  empty: "v1-state-empty",
  error: "v1-state-error",
  noPermission: "v1-state-no-permission",
} as const;
