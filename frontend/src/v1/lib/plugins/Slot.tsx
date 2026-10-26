import {
  Component,
  type ComponentType,
  type ErrorInfo,
  lazy,
  type ReactNode,
  Suspense,
} from "react";
import type { PluginRegistry } from "./registry";
import type { SlotId, SlotProps } from "./types";

export type PluginErrorReporter = (
  owner: string,
  slot: SlotId,
  error: unknown,
) => void;

export interface SlotComponentProps<K extends SlotId> {
  id: K;
  props: SlotProps[K];
  /** Shown when no plugin fills the slot, while it loads, and if it fails. */
  fallback: ReactNode;
}

interface BoundaryProps {
  fallback: ReactNode;
  onError: (error: unknown) => void;
  children: ReactNode;
}

class SlotBoundary extends Component<BoundaryProps, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  override componentDidCatch(error: unknown, _info: ErrorInfo): void {
    this.props.onError(error);
  }

  override render(): ReactNode {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

/**
 * The `<Slot>` component for one registry. Each slot gets its own error
 * boundary, so a plugin that fails to load or render shows that slot's
 * fallback and is reported, and every other slot keeps working.
 */
export function makeSlot(
  registry: PluginRegistry,
  report: PluginErrorReporter,
): <K extends SlotId>(p: SlotComponentProps<K>) => ReactNode {
  const fillers = new Map<SlotId, ComponentType<never>>();

  function filler<K extends SlotId>(id: K): ComponentType<SlotProps[K]> | null {
    const entry = registry.slot(id);
    if (!entry) {
      return null;
    }
    if (!fillers.has(id)) {
      fillers.set(id, lazy(entry.load) as ComponentType<never>);
    }
    return fillers.get(id) as ComponentType<SlotProps[K]>;
  }

  return function Slot<K extends SlotId>({
    id,
    props,
    fallback,
  }: SlotComponentProps<K>): ReactNode {
    const Filler = filler(id);
    if (!Filler) {
      return fallback;
    }
    const owner = registry.slot(id)?.owner ?? "unknown";
    return (
      <SlotBoundary fallback={fallback} onError={(e) => report(owner, id, e)}>
        <Suspense fallback={fallback}>
          <Filler {...props} />
        </Suspense>
      </SlotBoundary>
    );
  };
}
