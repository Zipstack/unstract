/*
 * Public entry of the v1 frontend — the only v1 module v0 may import, as
 * `@v1`. Lint rejects any other v0 → v1 import (see src/v1/README.md).
 *
 * Keep this light: v0 loads it eagerly, so it holds the version switch and
 * the registry, and the v1 tree itself loads only when a v1 page renders.
 */

import { LIVE_REGISTRY, V1_DEV_ROUTES } from "@v1/app/registry/live";
import { resolvePageUrl } from "@v1/app/registry/resolve";
import type { PageKey } from "@v1/app/registry/types";
import { useOldVersionStore } from "@v1/stores/oldVersion";

export { VersionSwitch, type VersionSwitchProps } from "@v1/app/VersionSwitch";

/** True in a build with the development-only demo routes (VITE_V1_DEV_ROUTES). */
export const v1DevRoutesEnabled: boolean = V1_DEV_ROUTES;

/**
 * Sets the signed-in user's old-version preference, which only Human Review
 * honours (D14). The version switch then moves the user to the equivalent
 * screen without a reload. False, and no change, while no user is known.
 * For the switch controls on both versions of Human Review (P6-T07).
 */
export function setOldVersion(on: boolean): boolean {
  return useOldVersionStore.getState().setOldVersion(on);
}

/**
 * The URL that opens `page` at one of its v1 route patterns, in the version
 * the user gets: the v1 URL when the page is live, else its mapped v0 URL.
 * Null when the page is not declared or that route has no v0 mapping.
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

export type {
  Distribution,
  PageKey,
  RegistryEntry,
} from "@v1/app/registry/types";
