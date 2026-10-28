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
  /** A new value clears an earlier failure, so a fresh filler gets a try. */
  resetKey: unknown;
  fallback: ReactNode;
  onError: (error: unknown) => void;
  children: ReactNode;
}

interface BoundaryState {
  failed: boolean;
  resetKey: unknown;
}

class SlotBoundary extends Component<BoundaryProps, BoundaryState> {
  override state: BoundaryState = {
    failed: false,
    resetKey: this.props.resetKey,
  };

  static getDerivedStateFromError(): Partial<BoundaryState> {
    return { failed: true };
  }

  static getDerivedStateFromProps(
    props: BoundaryProps,
    state: BoundaryState,
  ): Partial<BoundaryState> | null {
    return props.resetKey === state.resetKey
      ? null
      : { failed: false, resetKey: props.resetKey };
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
      // React caches a rejected lazy promise, so a failed load drops the
      // filler and the next render imports the chunk again.
      const lazyFiller = lazy(() =>
        entry.load().catch((err: unknown) => {
          if (fillers.get(id) === lazyFiller) {
            fillers.delete(id);
          }
          throw err;
        }),
      ) as ComponentType<never>;
      fillers.set(id, lazyFiller);
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
      <SlotBoundary
        resetKey={Filler}
        fallback={fallback}
        onError={(e) => report(owner, id, e)}
      >
        <Suspense fallback={fallback}>
          <Filler {...props} />
        </Suspense>
      </SlotBoundary>
    );
  };
}
