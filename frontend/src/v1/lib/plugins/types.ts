import type { ComponentType } from "react";

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
] as const;
export type SlotId = (typeof SLOT_IDS)[number];

/*
 * The props a filler receives; the host passes them.
 * ponytail: props are empty until the host page that renders each slot is
 * built; that task adds the fields it passes.
 */
export type SlotProps = { [K in SlotId]: Record<string, never> };

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
