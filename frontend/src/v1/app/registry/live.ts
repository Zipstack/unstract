/*
 * The registry this build and browser run with: the pure data in ./entries,
 * narrowed by build flags and the dev/test preview override.
 */

import { DEMO_PAGES, PAGES, REGISTERED_PAGES } from "./entries";
import { activeEntries } from "./resolve";
import {
  DISTRIBUTIONS,
  type Distribution,
  type PageKey,
  PREVIEW_STORAGE_KEY,
  type RegistryEntry,
} from "./types";
import { isPageKey, registryProblems } from "./validate";

/**
 * VITE_V1_DEV_ROUTES=true registers the demo pages and honours the preview
 * override. Set only for the E2E image and local development, never in a
 * release build.
 */
export const V1_DEV_ROUTES: boolean =
  import.meta.env.VITE_V1_DEV_ROUTES === "true";

// Declared in types.ts so the E2E harness can import it without Vite.
export { PREVIEW_STORAGE_KEY };

/**
 * The build's distribution from VITE_DISTRIBUTION: OSS when unset,
 * null when the value is not a distribution. vite.config.js fails the build
 * on such a value, so null is reached only by a build that skipped it.
 */
export function parseDistribution(
  raw: string | undefined,
): Distribution | null {
  const value = raw?.trim().toLowerCase() || "oss";
  return DISTRIBUTIONS.find((d) => d === value) ?? null;
}

/** Valid page keys in the preview override; anything unreadable or malformed means none. */
export function readPreviewPages(
  storage: Pick<Storage, "getItem"> | null | undefined,
): PageKey[] {
  try {
    const parsed: unknown = JSON.parse(
      storage?.getItem(PREVIEW_STORAGE_KEY) ?? "[]",
    );
    return Array.isArray(parsed) ? parsed.filter(isPageKey) : [];
  } catch {
    return [];
  }
}

export type LiveRegistry = Readonly<{
  /** Every page declared in this build, live or not. */
  pages: readonly RegistryEntry[];
  /** The pages that render as v1. */
  entries: readonly RegistryEntry[];
}>;

export function buildLiveRegistry(options: {
  devRoutes: boolean;
  distribution: Distribution;
  storage: Pick<Storage, "getItem"> | null;
}): LiveRegistry {
  const { devRoutes, distribution, storage } = options;
  const pages = devRoutes ? [...PAGES, ...DEMO_PAGES] : [...PAGES];
  const live = new Set<PageKey>(REGISTERED_PAGES);
  if (devRoutes) {
    for (const key of [
      ...DEMO_PAGES.map((p) => p.page),
      ...readPreviewPages(storage),
    ]) {
      live.add(key);
    }
  }
  return { pages, entries: activeEntries(pages, live, distribution) };
}

function browserStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function load(): LiveRegistry {
  const raw = import.meta.env.VITE_DISTRIBUTION;
  let distribution = parseDistribution(raw);
  if (distribution === null) {
    // Never blank the app over it: v0 loads this module eagerly.
    console.error(
      `VITE_DISTRIBUTION=${raw} is not one of ${DISTRIBUTIONS.join(", ")}; using oss`,
    );
    distribution = "oss";
  }
  const registry = buildLiveRegistry({
    devRoutes: V1_DEV_ROUTES,
    distribution,
    storage: browserStorage(),
  });
  // CI rejects an invalid registry through validate.test.ts; development
  // builds fail loudly too. Release builds skip the check (and its code).
  if (import.meta.env.DEV) {
    const problems = registryProblems(registry.pages);
    if (problems.length) {
      throw new Error(`Invalid v1 route registry:\n${problems.join("\n")}`);
    }
  }
  return registry;
}

/** Read once at load: the preview override is set before the app starts. */
export const LIVE_REGISTRY: LiveRegistry = load();
