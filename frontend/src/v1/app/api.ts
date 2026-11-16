/*
 * The helpers the public entry (`@v1`, src/v1/index.ts) exposes to v0. They
 * live here so v1 code and tests can import them without the entry.
 */

import { LIVE_REGISTRY, V1_DEV_ROUTES } from "@v1/app/registry/live";
import { resolvePageUrl } from "@v1/app/registry/resolve";
import type { PageKey } from "@v1/app/registry/types";
import { useOldVersionStore } from "@v1/stores/oldVersion";

/** True in a build with the development-only demo routes (VITE_V1_DEV_ROUTES). */
export const v1DevRoutesEnabled: boolean = V1_DEV_ROUTES;

/**
 * Sets the signed-in user's old-version preference, which only Human Review
 * honours (D14). The version switch then moves the user to the equivalent
 * screen without a reload. True once set; if storage refuses the write, the
 * choice lasts for this session only. False, and no change, while no user is
 * known.
 * For the switch controls on both versions of Human Review (P6-T07).
 */
export function setOldVersion(on: boolean): boolean {
  return useOldVersionStore.getState().setOldVersion(on);
}

/**
 * The URL that opens `page` at one of its v1 route patterns, in the version
 * the user gets: the v1 URL when the page is live (unless it is Human Review
 * and the user chose the old version), else its mapped v0 URL. Params are raw
 * values and are encoded here. Null when the page is not declared, the
 * pattern is not one of its v1 routes, or a `:param` of the pattern is missing
 * or empty. Reads the preference when called, so it does not re-render on
 * its own. Before the session loads it uses the choice of the last user known
 * to this browser, as the switch does. In the one render where a newly
 * signed-in user is not yet synced to the store (a layout effect, before
 * paint), it can still give the previous user's choice; the switch masks it.
 *
 *   resolveUrl("UN05", "/:orgName/workflows/:id", { orgName, id })
 */
export function resolveUrl(
  page: PageKey,
  v1Pattern: string,
  params: Readonly<Record<string, string>>,
): string | null {
  return resolvePageUrl(page, v1Pattern, params, LIVE_REGISTRY.pages, {
    entries: LIVE_REGISTRY.entries,
    oldVersion: useOldVersionStore.getState().oldVersion,
  });
}
