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
  "prompt-studio.settings.summarized-extraction",
  "prompt-studio.settings.llm-challenge",
  "prompt-studio.settings.highlighting",
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

/**
 * A Prompt Studio Settings section (Summarized Extraction, LLM Challenge,
 * Highlighting). The filler renders the whole section, heading included,
 * with `id={anchorId}`. It saves only its own fields through
 * `PATCH prompt-studio/{toolId}/` and writes the response to the project's
 * cached detail (after cancelling any read of it in flight, so an older read
 * cannot land on top), so other sections see it. It reports unsaved changes, and
 * `false` when it unmounts, so the tab asks before they are lost and only then.
 */
export type SettingsSectionProps = Readonly<{
  toolId: string;
  /** Show the saved values without save controls (public share). */
  readOnly: boolean;
  /** The id the section's root element takes, so the section list can link to it. */
  anchorId: string;
  onDirtyChange: (dirty: boolean) => void;
}>;

/** The Prompt Studio Settings tab's slots. */
export type SettingsSlotId = Extract<
  SlotId,
  `prompt-studio.settings.${string}`
>;

/** Non-gate slots whose host passes props: every settings slot gets SettingsSectionProps. */
type HostProps = { [K in SettingsSlotId]: SettingsSectionProps };

/*
 * The props a filler receives; the host passes them.
 * ponytail: any other slot's props stay empty until the host page that
 * renders it is built; that task adds the slot to HostProps.
 */
export type SlotProps = {
  [K in SlotId]: K extends GateSlotId
    ? GateProps
    : K extends keyof HostProps
      ? HostProps[K]
      : Record<string, never>;
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
