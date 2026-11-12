/*
 * Builds the plugin registry from the manifests the cloud overlay copies in
 * as `plugins/<id>/manifest.ts`. An absent plugin has no manifest, so its
 * slots show their fallbacks; every import error left is a real failure and
 * is reported. Nothing renders `PluginSlot` or `pluginRoutes()` yet: the v1
 * shell (P2-T01) wraps the app in `PluginProvider` with `PluginSlot` and adds
 * the plugin routes to the v1 router.
 */
import { DEMO_PAGES, PAGES } from "@v1/app/registry/entries";
import { patternsOverlap } from "@v1/app/registry/patterns";
import { notify } from "@v1/lib/notify";
import {
  buildRegistry,
  type Distribution,
  makeSlot,
  type PluginErrorReporter,
  type PluginManifest,
  type PluginRegistry,
  type RouteEntry,
} from "@v1/lib/plugins";

const DISTRIBUTIONS: readonly Distribution[] = ["oss", "cloud", "onprem"];

function currentDistribution(): Distribution {
  // Empty means oss: the frontend image passes the build arg through even when unset.
  const value =
    import.meta.env.VITE_DISTRIBUTION?.trim().toLowerCase() || "oss";
  if (!DISTRIBUTIONS.includes(value)) {
    throw new Error(
      `VITE_DISTRIBUTION must be one of ${DISTRIBUTIONS.join(", ")}; got ${value}`,
    );
  }
  return value;
}

const manifests = Object.values(
  import.meta.glob<PluginManifest>("./*/manifest.ts", {
    eager: true,
    import: "manifest",
  }),
);

// Demo pages count: an E2E build registers them.
const OSS_ROUTES = [...PAGES, ...DEMO_PAGES].flatMap((page) => page.v1Routes);

/** The registry for these manifests; a plugin route on an OSS page throws. */
export function pluginRegistry(
  list: readonly PluginManifest[],
  distribution: Distribution,
): PluginRegistry {
  return buildRegistry(list, distribution, OSS_ROUTES, patternsOverlap);
}

export const registry = pluginRegistry(manifests, currentDistribution());

/** Logs the failure and raises one error notification per plugin slot. */
export const reportPluginError: PluginErrorReporter = (owner, slot, error) => {
  console.error(`v1 plugin ${owner} failed in slot ${slot}`, error);
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
