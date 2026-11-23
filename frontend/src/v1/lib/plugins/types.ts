import type { ComponentType, ReactNode } from "react";

/*
 * Plugin manifests import from here with `import type`, so the build check in
 * scripts/v1-plugins.mjs can load a manifest without bundling it. The runtime
 * lists below let the registry reject a value tsc never saw.
 */

/** Builds a cloud plugin can ship in. The public OSS build has no plugins. */
export const PLUGIN_DISTRIBUTIONS = ["cloud", "onprem"] as const;
export type PluginDistribution = (typeof PLUGIN_DISTRIBUTIONS)[number];
export type Distribution = "oss" | PluginDistribution;

/** Every extension point. Adding a slot is one line here. */
export const SLOT_IDS = [
  "prompt-studio.lookups",
  "prompt-studio.cloud-tools",
  "workflows.human-review",
  "account-menu.plan-billing",
  "shell.product-switcher",
  "platform.hitl-keys",
  "platform.hitl-settings",
  "dashboard.subscription-usage",
  "dashboard.attention-items",
  "route.entitlement",
  "route.platform-admin",
] as const;
export type SlotId = (typeof SLOT_IDS)[number];

/**
 * Route gates: the filler renders `children` (the page) when the
 * user may see it, else its own screen. `route.entitlement` wraps every
 * signed-in page (cloud: onboarding, subscription, trial); its fallback is the
 * page. `route.platform-admin` wraps platform-admin pages; its fallback is
 * the no-permission state.
 */
export const GATE_SLOT_IDS = [
  "route.entitlement",
  "route.platform-admin",
] as const satisfies readonly SlotId[];
export type GateSlotId = (typeof GATE_SLOT_IDS)[number];

export type GateProps = Readonly<{ children: ReactNode }>;

/*
 * The props a filler receives; the host passes them.
 * ponytail: props are empty until the host page that renders each slot is
 * built; that task adds the fields it passes.
 */
export type SlotProps = {
  [K in SlotId]: K extends GateSlotId ? GateProps : Record<string, never>;
};

export type ComponentLoader<P> = () => Promise<{ default: ComponentType<P> }>;

export interface PluginRoute {
  path: string;
  load: ComponentLoader<Record<string, never>>;
}

export interface PluginManifest {
  id: string;
  distributions: readonly PluginDistribution[];
  slots?: { [K in SlotId]?: ComponentLoader<SlotProps[K]> };
  routes?: readonly PluginRoute[];
}
