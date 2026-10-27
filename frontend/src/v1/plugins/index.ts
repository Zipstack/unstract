/*
 * Builds the plugin registry from the manifests the cloud overlay copies in
 * as `plugins/<id>/manifest.ts`. An absent plugin has no manifest, so its
 * slots show their fallbacks; every import error left is a real failure and
 * is reported. `app/` passes `PluginSlot` to `PluginProvider` and
 * `pluginRoutes()` to the router.
 */
import {
  buildRegistry,
  type Distribution,
  makeSlot,
  type PluginErrorReporter,
  type PluginManifest,
  type RouteEntry,
} from "@v1/lib/plugins";

const DISTRIBUTIONS: readonly Distribution[] = ["oss", "cloud", "onprem"];

function currentDistribution(): Distribution {
  const value = import.meta.env.VITE_DISTRIBUTION ?? "oss";
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

export const registry = buildRegistry(manifests, currentDistribution());

// ponytail: logs only; the v1 notification contract adds the toast here.
const report: PluginErrorReporter = (owner, slot, error) => {
  console.error(`v1 plugin ${owner} failed in slot ${slot}`, error);
};

export const PluginSlot = makeSlot(registry, report);

/** Routes contributed by plugins in this distribution, for the v1 router. */
export function pluginRoutes(): readonly RouteEntry[] {
  return registry.routes;
}
