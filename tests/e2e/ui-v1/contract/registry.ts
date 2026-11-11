/**
 * The ONE place the harness learns about the v1 route registry (P0-T03,
 * UN-4271). The redirect, old-version and preview helpers read it only
 * through this module.
 *
 * It imports the frontend's own registry data, so the harness and the app
 * cannot drift. registry/types.ts promises that types.ts, entries.ts and
 * lib/oldVersion.ts stay importable without Vite (no `import.meta.env`, no
 * `@v1` alias, only relative imports). This also reads registry/validate.ts
 * (via patterns.ts) and, in v1-ui.ts, lib/theme.ts, which hold to the same
 * today without promising it; if one stops, every run fails at load, not
 * silently. registry/live.ts reads `import.meta.env` when it loads, so this
 * module rebuilds what it would compute for the E2E image instead.
 *
 * The harness's distribution (UNSTRACT_DISTRIBUTION) must match the image's
 * (VITE_DISTRIBUTION; unset means oss): nothing can check that from here.
 */

import {
  DEMO_PAGES,
  PAGES,
  REGISTERED_PAGES,
} from "../../../../frontend/src/v1/app/registry/entries.ts";
import {
  type Distribution,
  type PageKey,
  PREVIEW_STORAGE_KEY,
  type RegistryEntry,
} from "../../../../frontend/src/v1/app/registry/types.ts";

export type {
  Distribution,
  PageKey,
  RegistryEntry,
} from "../../../../frontend/src/v1/app/registry/types.ts";
export {
  isPageKey,
  TOGGLE_PAGES,
} from "../../../../frontend/src/v1/app/registry/validate.ts";
export {
  LAST_USER_STORAGE_KEY,
  OLD_VERSION_ON,
  oldVersionStorageKey,
} from "../../../../frontend/src/v1/lib/oldVersion.ts";

function isRegistered(entry: RegistryEntry): boolean {
  return REGISTERED_PAGES.includes(entry.page);
}

/**
 * The pages the E2E image renders as v1: registered pages, plus the
 * development-only demo pages, which VITE_V1_DEV_ROUTES=true (set for the
 * E2E image in ci-test.yaml) makes live.
 */
export const REGISTRY: readonly RegistryEntry[] = [
  ...PAGES.filter(isRegistered),
  ...DEMO_PAGES,
];

/**
 * Declared but not yet registered (D9): these render as v1 only through the
 * preview override (`test.use({ v1Preview: [...] })`), and only in a build
 * of a distribution they list (the app's activeEntries drops the rest).
 */
export const UNREGISTERED_PAGES: readonly RegistryEntry[] = PAGES.filter(
  (entry) => !isRegistered(entry),
);

/** Whether `entry` can render as v1 in a build of `distribution`. */
export function shipsIn(
  entry: RegistryEntry,
  distribution: Distribution,
): boolean {
  return entry.distributions.includes(distribution);
}

/** How a test asks the app to render pages before they are registered. */
export type PreviewMechanism =
  | { kind: "localStorage" | "sessionStorage"; key: string }
  | { kind: "cookie"; name: string };

/**
 * P0-T03's override: a JSON array of page keys in localStorage, read once
 * when the app loads, honoured only with VITE_V1_DEV_ROUTES=true.
 */
export const V1_PREVIEW: PreviewMechanism = {
  kind: "localStorage",
  key: PREVIEW_STORAGE_KEY,
};

/** Any declared page, registered or previewable. */
export function findEntry(page: PageKey): RegistryEntry {
  const entry = [...REGISTRY, ...UNREGISTERED_PAGES].find(
    (e) => e.page === page,
  );
  if (!entry) {
    throw new Error(`page ${page} is not declared in the v1 route registry`);
  }
  return entry;
}
