import type { ComponentType } from "react";

/*
 * Type-only module. Plugin manifests import from here with `import type`, so
 * Node and Bun can load a manifest without bundling it (the build check in
 * scripts/v1-plugins.mjs does exactly that).
 */

/** Builds a cloud plugin can ship in. The public OSS build has no plugins. */
export type PluginDistribution = "cloud" | "onprem";
export type Distribution = "oss" | PluginDistribution;

/*
 * Every extension point and its props. A filler receives these props; the
 * host passes them. Adding a slot is one line here.
 * ponytail: props are empty until the host page that renders each slot is
 * built; that task adds the fields it passes.
 */
export interface SlotProps {
  "prompt-studio.lookups": Record<string, never>;
  "prompt-studio.cloud-tools": Record<string, never>;
  "workflows.human-review": Record<string, never>;
  "account-menu.plan-billing": Record<string, never>;
  "shell.product-switcher": Record<string, never>;
  "platform.hitl-keys": Record<string, never>;
  "platform.hitl-settings": Record<string, never>;
  "dashboard.subscription-usage": Record<string, never>;
  "dashboard.attention-items": Record<string, never>;
}

export type SlotId = keyof SlotProps;

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
