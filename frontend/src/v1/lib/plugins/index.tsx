/*
 * v1's extension-point contract. Shell and pages render `<Slot>` from here;
 * they never import a plugin. The registry itself is built in
 * `@v1/plugins` (the only folder that may see plugin manifests). The v1 shell
 * (P2-T01) is to hand it down through `PluginProvider`; nothing does yet. With
 * no provider, as in OSS tests, every slot shows its fallback.
 */
import { createContext, type ReactNode, useContext } from "react";
import type { makeSlot, SlotComponentProps } from "./Slot";
import type { SlotId } from "./types";

export {
  buildRegistry,
  PluginConflictError,
  type PluginRegistry,
  type RouteEntry,
} from "./registry";
export {
  makeSlot,
  type PluginErrorReporter,
  type SlotComponentProps,
} from "./Slot";
export type * from "./types";

type SlotRenderer = ReturnType<typeof makeSlot>;

const SlotContext = createContext<SlotRenderer | null>(null);

export function PluginProvider({
  slot,
  children,
}: {
  slot: SlotRenderer;
  children: ReactNode;
}): ReactNode {
  return <SlotContext.Provider value={slot}>{children}</SlotContext.Provider>;
}

export function Slot<K extends SlotId>(p: SlotComponentProps<K>): ReactNode {
  const Render = useContext(SlotContext);
  return Render ? <Render {...p} /> : p.fallback;
}
