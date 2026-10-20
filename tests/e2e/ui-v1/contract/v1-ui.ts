/**
 * DOM markers the helpers assert on, in one place.
 *
 * ASSUMED, not yet published: the v1 tree root, its theme hook and the core
 * state components do not exist yet (P0-T01, P0-T04, P1). These are the
 * conventions the harness expects; when those tasks land, change the values
 * here (or have those tasks adopt them) and every helper follows.
 */

/** Attribute on the v1 tree root that tells v1 apart from v0. */
export const V1_ROOT_SELECTOR = '[data-ui-version="v1"]';

/**
 * Something rendered into the SPA mount (frontend/index.html `#root`). "No v1
 * root" only means v0 rendered once this exists; before React mounts, the
 * page has no v1 root either.
 */
export const APP_MOUNTED_SELECTOR = "#root > *";

/** Test ids of the one skeleton, empty state, error and no-permission view. */
export const STATE_TEST_IDS = {
  loading: "v1-state-loading",
  empty: "v1-state-empty",
  error: "v1-state-error",
  noPermission: "v1-state-no-permission",
} as const;

export const THEMES = ["light", "dark", "unstract"] as const;
export type Theme = (typeof THEMES)[number];

/**
 * Default theme hook (P0-T04 owns the real one): a `data-theme` attribute plus
 * a same-named class on <html>, which covers both the attribute and the
 * Tailwind class strategy.
 */
export const THEME_ATTRIBUTE = "data-theme";
