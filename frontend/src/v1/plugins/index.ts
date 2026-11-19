/*
 * Builds the plugin registry from the manifests the cloud overlay copies in
 * as `plugins/<id>/manifest.ts`. An absent plugin has no manifest, so its
 * slots show their fallbacks; a filler that fails to load or render is
 * reported. `V1App` provides `PluginSlot`; nothing adds `pluginRoutes()` to
 * the v1 router yet (the v1 shell).
 */
import { DEMO_PAGES, PAGES } from "@v1/app/registry/entries";
import { patternProblem, patternsOverlap } from "@v1/app/registry/patterns";
import { DISTRIBUTIONS } from "@v1/app/registry/types";
import { notify } from "@v1/lib/notify";
import {
  buildRegistry,
  type Distribution,
  GATE_SLOT_IDS,
  makeSlot,
  type PluginErrorReporter,
  type PluginManifest,
  type PluginRegistry,
  type RouteEntry,
  type SlotId,
} from "@v1/lib/plugins";

function currentDistribution(): Distribution {
  // Empty means oss: the frontend image passes the build arg through even when unset.
  const value =
    import.meta.env.VITE_DISTRIBUTION?.trim().toLowerCase() || "oss";
  const distribution = DISTRIBUTIONS.find((d) => d === value);
  if (!distribution) {
    throw new Error(
      `VITE_DISTRIBUTION must be one of ${DISTRIBUTIONS.join(", ")}; got ${value}`,
    );
  }
  return distribution;
}

const manifests = Object.values(
  import.meta.glob<PluginManifest>("./*/manifest.ts", {
    eager: true,
    import: "manifest",
  }),
);

// Demo pages count: an E2E build registers them.
const OSS_ROUTES = [...PAGES, ...DEMO_PAGES].flatMap((page) => page.v1Routes);

/**
 * The registry for these manifests. A plugin route on an OSS page, or one the
 * route registry's pattern rule rejects, throws.
 */
export function pluginRegistry(
  list: readonly PluginManifest[],
  distribution: Distribution,
): PluginRegistry {
  return buildRegistry(list, distribution, {
    ossRoutes: OSS_ROUTES,
    overlaps: patternsOverlap,
    patternProblem,
  });
}

export const registry = pluginRegistry(manifests, currentDistribution());

const isGate = (slot: SlotId): boolean =>
  (GATE_SLOT_IDS as readonly SlotId[]).includes(slot);

/** Logs the failure and raises one error notification per plugin slot; a route gate shows its own alert instead. */
export const reportPluginError: PluginErrorReporter = (owner, slot, error) => {
  console.error(`v1 plugin ${owner} failed in slot ${slot}`, error);
  if (isGate(slot)) {
    return;
  }
  notify({
    kind: "error",
    title: "Part of this page could not load.",
    description: "Reload the page to try again.",
    // Reusing the id replaces an open notification instead of stacking.
    id: `plugin-${owner}-${slot}`,
  });
};

export const PluginSlot = makeSlot(registry, reportPluginError);

/** Routes contributed by plugins in this distribution, for the v1 router. */
export function pluginRoutes(): readonly RouteEntry[] {
  return registry.routes;
}
