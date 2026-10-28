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

function assertDeclared(manifests: readonly PluginManifest[]): void {
  const seen = new Set<string>();
  for (const m of manifests) {
    if (seen.has(m.id)) {
      throw new PluginConflictError(`plugin id ${m.id} is used twice`);
    }
    seen.add(m.id);
    if (m.distributions.length === 0) {
      throw new PluginConflictError(`${m.id} declares no distributions`);
    }
    for (const d of m.distributions as readonly string[]) {
      if (!(PLUGIN_DISTRIBUTIONS as readonly string[]).includes(d)) {
        throw new PluginConflictError(
          `${m.id} declares unknown distribution ${d}`,
        );
      }
    }
    for (const id of Object.keys(m.slots ?? {})) {
      if (!(SLOT_IDS as readonly string[]).includes(id)) {
        throw new PluginConflictError(`${m.id} fills unknown slot ${id}`);
      }
    }
  }
}

function collect(
  manifests: readonly PluginManifest[],
  ossRoutes: readonly string[],
): { slots: Map<SlotId, SlotEntry<SlotId>>; routes: RouteEntry[] } {
  const slots = new Map<SlotId, SlotEntry<SlotId>>();
  const routeOwners = new Map<string, string>(
    ossRoutes.map((path) => [path, "OSS"]),
  );
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
      const taken = routeOwners.get(route.path);
      if (taken) {
        throw new PluginConflictError(
          `route ${route.path} is defined by both ${taken} and ${m.id}`,
        );
      }
      routeOwners.set(route.path, m.id);
      routes.push({ ...route, owner: m.id });
    }
  }
  return { slots, routes };
}

/**
 * The plugins, slots and routes one distribution offers. Throws
 * PluginConflictError when any distribution would have a slot filled twice,
 * a route defined twice, a plugin that declares nowhere to ship, or a
 * manifest naming a slot or distribution that does not exist.
 */
export function buildRegistry(
  manifests: readonly PluginManifest[],
  distribution: Distribution,
  ossRoutes: readonly string[] = [],
): PluginRegistry {
  assertDeclared(manifests);
  const inDistribution = (d: Distribution) =>
    manifests.filter((m) =>
      (m.distributions as readonly Distribution[]).includes(d),
    );
  for (const d of PLUGIN_DISTRIBUTIONS) {
    collect(inDistribution(d), ossRoutes);
  }
  const offered = inDistribution(distribution);
  const { slots, routes } = collect(offered, ossRoutes);
  return {
    distribution,
    plugins: offered.map((m) => m.id),
    routes,
    slot: <K extends SlotId>(id: K) =>
      slots.get(id) as SlotEntry<K> | undefined,
  };
}
