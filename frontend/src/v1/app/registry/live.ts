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
  type RegistryEntry,
} from "./types";
import { registryProblems } from "./validate";

/**
 * VITE_V1_DEV_ROUTES=true registers the demo pages and honours the preview
 * override. Set only for the E2E image and local development, never in a
 * release build.
 */
export const V1_DEV_ROUTES: boolean =
  import.meta.env.VITE_V1_DEV_ROUTES === "true";

/**
 * Dev/test override: a JSON array of declared page keys to render as v1
 * before they are registered (D9), e.g. `["UN05"]`. Honoured only with
 * V1_DEV_ROUTES.
 */
export const PREVIEW_STORAGE_KEY = "unstract.v1.preview";

function isDistribution(value: unknown): value is Distribution {
  return (DISTRIBUTIONS as readonly unknown[]).includes(value);
}

/** The build's distribution, from VITE_UNSTRACT_DISTRIBUTION; OSS when unset. */
export function parseDistribution(raw: string | undefined): Distribution {
  const value = raw?.trim().toLowerCase() || "oss";
  if (!isDistribution(value)) {
    throw new Error(
      `VITE_UNSTRACT_DISTRIBUTION=${raw} is not one of ${DISTRIBUTIONS.join(", ")}`,
    );
  }
  return value;
}

/** Page keys in the preview override; anything unreadable or malformed means none. */
export function readPreviewPages(
  storage: Pick<Storage, "getItem"> | null | undefined,
): PageKey[] {
  try {
    const parsed: unknown = JSON.parse(
      storage?.getItem(PREVIEW_STORAGE_KEY) ?? "[]",
    );
    return Array.isArray(parsed)
      ? parsed.filter((k): k is PageKey => typeof k === "string")
      : [];
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
  const registry = buildLiveRegistry({
    devRoutes: V1_DEV_ROUTES,
    distribution: parseDistribution(import.meta.env.VITE_UNSTRACT_DISTRIBUTION),
    storage: browserStorage(),
  });
  // CI rejects an invalid registry through its unit test; fail loudly in development too.
  const problems = registryProblems(registry.pages);
  if (import.meta.env.DEV && problems.length) {
    throw new Error(`Invalid v1 route registry:\n${problems.join("\n")}`);
  }
  return registry;
}

/** Read once at load: the preview override is set before the app starts. */
export const LIVE_REGISTRY: LiveRegistry = load();
