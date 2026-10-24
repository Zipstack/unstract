/*
 * v1's extension points. Plugins are found at build time from
 * src/v1/plugins/<id>/manifest.ts (copied in by the cloud overlay), so an
 * absent plugin has no manifest and its slots show their fallbacks. Every
 * import error left is a real failure and is reported.
 */
import { buildRegistry, type RouteEntry } from "./registry";
import { makeSlot, type PluginErrorReporter } from "./Slot";
import type { Distribution, PluginManifest } from "./types";

export type { SlotComponentProps } from "./Slot";
export type * from "./types";

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
  import.meta.glob<PluginManifest>("../../plugins/*/manifest.ts", {
    eager: true,
    import: "manifest",
  }),
);

export const registry = buildRegistry(manifests, currentDistribution());

// ponytail: logs only; the v1 notification contract adds the toast here.
const report: PluginErrorReporter = (owner, slot, error) => {
  console.error(`v1 plugin ${owner} failed in slot ${slot}`, error);
};

export const Slot = makeSlot(registry, report);

/** Routes contributed by plugins in this distribution, for the v1 router. */
export function pluginRoutes(): readonly RouteEntry[] {
  return registry.routes;
}
