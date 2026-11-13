import {
  type ComponentLoader,
  type Distribution,
  PLUGIN_DISTRIBUTIONS,
  type PluginManifest,
  type PluginRoute,
  SLOT_IDS,
  type SlotId,
  type SlotProps,
} from "./types";

export class PluginConflictError extends Error {
  override name = "PluginConflictError";
}

export interface SlotEntry<K extends SlotId> {
  owner: string;
  load: ComponentLoader<SlotProps[K]>;
}

export interface RouteEntry extends PluginRoute {
  owner: string;
}

export interface PluginRegistry {
  distribution: Distribution;
  plugins: readonly string[];
  routes: readonly RouteEntry[];
  slot<K extends SlotId>(id: K): SlotEntry<K> | undefined;
}

/** True when some URL matches both route patterns. */
export type RouteOverlap = (a: string, b: string) => boolean;

/** Why a route pattern is not accepted, or null. */
export type PatternProblem = (pattern: string) => string | null;

/** How plugin routes are checked; the app passes the route registry's rules. */
export interface RouteRules {
  /** Route patterns of OSS pages; a plugin route may not overlap one. */
  ossRoutes?: readonly string[];
  /** Default: two paths overlap only when they are equal. */
  overlaps?: RouteOverlap;
  /** Default: a path must start with `/`. */
  patternProblem?: PatternProblem;
}

const samePath: RouteOverlap = (a, b) => a === b;

const absolute: PatternProblem = (pattern) =>
  pattern.startsWith("/") ? null : "must start with /";

function fail(message: string): never {
  throw new PluginConflictError(message);
}

/*
 * tsc never sees a manifest the cloud overlay copies in, so its shape is
 * checked here at run time.
 */
function assertShape(m: PluginManifest, patternProblem: PatternProblem): void {
  for (const [id, load] of Object.entries(m.slots ?? {})) {
    if (!(SLOT_IDS as readonly string[]).includes(id)) {
      fail(`${m.id} fills unknown slot ${id}`);
    }
    if (typeof load !== "function") {
      fail(
        `${m.id} fills slot ${id} with ${typeof load}, not a loader function`,
      );
    }
  }
  for (const [i, route] of (m.routes ?? []).entries()) {
    const path: unknown = route?.path;
    if (typeof path !== "string") {
      fail(`${m.id} route ${i} has no string path`);
    }
    if (typeof route.load !== "function") {
      fail(`${m.id} route ${path} has no load function`);
    }
    const problem = patternProblem(path);
    if (problem) {
      fail(`${m.id} route ${path} is not accepted: ${problem}`);
    }
  }
}

function assertDeclared(
  manifests: readonly PluginManifest[],
  patternProblem: PatternProblem,
): void {
  const seen = new Set<string>();
  for (const m of manifests) {
    if (seen.has(m.id)) {
      fail(`plugin id ${m.id} is used twice`);
    }
    seen.add(m.id);
    if (m.distributions.length === 0) {
      fail(`${m.id} declares no distributions`);
    }
    for (const d of m.distributions as readonly string[]) {
      if (!(PLUGIN_DISTRIBUTIONS as readonly string[]).includes(d)) {
        fail(`${m.id} declares unknown distribution ${d}`);
      }
    }
    assertShape(m, patternProblem);
  }
}

function collect(
  manifests: readonly PluginManifest[],
  ossRoutes: readonly string[],
  overlaps: RouteOverlap,
): { slots: Map<SlotId, SlotEntry<SlotId>>; routes: RouteEntry[] } {
  const slots = new Map<SlotId, SlotEntry<SlotId>>();
  const owned: [path: string, owner: string][] = ossRoutes.map((path) => [
    path,
    "OSS",
  ]);
  const routes: RouteEntry[] = [];
  for (const m of manifests) {
    for (const [id, load] of Object.entries(m.slots ?? {})) {
      const slotId = id as SlotId;
      const taken = slots.get(slotId);
      if (taken) {
        throw new PluginConflictError(
          `slot ${slotId} is filled by both ${taken.owner} and ${m.id}`,
        );
      }
      slots.set(slotId, {
        owner: m.id,
        load: load as ComponentLoader<SlotProps[SlotId]>,
      });
    }
    for (const route of m.routes ?? []) {
      const taken = owned.find(([path]) => overlaps(path, route.path));
      if (taken) {
        const [path, owner] = taken;
        const what =
          path === route.path ? route.path : `${route.path} (overlaps ${path})`;
        throw new PluginConflictError(
          `route ${what} is defined by both ${owner} and ${m.id}`,
        );
      }
      owned.push([route.path, m.id]);
      routes.push({ ...route, owner: m.id });
    }
  }
  return { slots, routes };
}

/**
 * The plugins, slots and routes one distribution offers. Throws
 * PluginConflictError when any distribution would have a slot filled twice,
 * a route defined twice, a plugin that declares nowhere to ship, a manifest
 * naming a slot or distribution that does not exist, a slot or route whose
 * loader is not a function, or a route path `patternProblem` rejects.
 *
 * Two routes clash when `overlaps` says some URL matches both. The app passes
 * the route registry's `patternsOverlap` and `patternProblem` (lib/ cannot
 * import app/), so params, case and splats count, and only patterns that
 * check can stay exact are let in.
 */
export function buildRegistry(
  manifests: readonly PluginManifest[],
  distribution: Distribution,
  {
    ossRoutes = [],
    overlaps = samePath,
    patternProblem = absolute,
  }: RouteRules = {},
): PluginRegistry {
  assertDeclared(manifests, patternProblem);
  const inDistribution = (d: Distribution) =>
    manifests.filter((m) =>
      (m.distributions as readonly Distribution[]).includes(d),
    );
  for (const d of PLUGIN_DISTRIBUTIONS) {
    collect(inDistribution(d), ossRoutes, overlaps);
  }
  const offered = inDistribution(distribution);
  const { slots, routes } = collect(offered, ossRoutes, overlaps);
  return {
    distribution,
    plugins: offered.map((m) => m.id),
    routes,
    slot: <K extends SlotId>(id: K) =>
      slots.get(id) as SlotEntry<K> | undefined,
  };
}
