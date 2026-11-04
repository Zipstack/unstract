/*
 * The version switch (UN-4271): renders v0 or v1 per URL. v0's router mounts
 * it around its own routes, as `children`, which render untouched whenever
 * the URL resolves to v0.
 */

import { LIVE_REGISTRY, type LiveRegistry } from "@v1/app/registry/live";
import { resolveRoute } from "@v1/app/registry/resolve";
import type { RegistryEntry } from "@v1/app/registry/types";
import { useOldVersionStore } from "@v1/stores/oldVersion";
import {
  Component,
  type JSX,
  lazy,
  type ReactNode,
  Suspense,
  useLayoutEffect,
} from "react";
import { Navigate, useLocation } from "react-router-dom";

const V1App = lazy(() => import("./V1App").then((m) => ({ default: m.V1App })));

export type VersionSwitchProps = Readonly<{
  /** The signed-in user's id from the v0 session; null or absent while signed out. */
  userId?: string | number | null;
  /** The v0 app, rendered when the URL resolves to v0. */
  children: ReactNode;
  /** For tests; defaults to this build's registry. */
  registry?: LiveRegistry;
}>;

type BoundaryState = { failed: boolean };

/** Keeps a v1 failure (a stale chunk after a deploy) from unmounting the whole app. */
class V1ErrorBoundary extends Component<
  { children: ReactNode },
  BoundaryState
> {
  override state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  override render(): ReactNode {
    if (this.state.failed) {
      return (
        <p className="ui:p-6" role="alert">
          This page could not be loaded. Reload to try again.
        </p>
      );
    }
    return this.props.children;
  }
}

function V1Root({ entry }: Readonly<{ entry: RegistryEntry }>): JSX.Element {
  return (
    <V1ErrorBoundary key={entry.page}>
      <Suspense fallback={null}>
        <V1App entry={entry} />
      </Suspense>
    </V1ErrorBoundary>
  );
}

function toUserId(userId: string | number | null | undefined): string | null {
  return userId === undefined || userId === null || userId === ""
    ? null
    : String(userId);
}

export function VersionSwitch({
  userId,
  children,
  registry = LIVE_REGISTRY,
}: VersionSwitchProps): JSX.Element {
  const location = useLocation();
  const user = toUserId(userId);
  const storeUser = useOldVersionStore((s) => s.userId);
  const storedChoice = useOldVersionStore((s) => s.oldVersion);

  useLayoutEffect(() => {
    useOldVersionStore.getState().setUser(user);
  }, [user]);

  // Until the store has caught up with a newly signed-in user, their choice
  // is unknown, so the previous user's never redirects them.
  const oldVersion = user !== null && user !== storeUser ? null : storedChoice;
  const resolution = resolveRoute(location, {
    entries: registry.entries,
    oldVersion,
  });

  switch (resolution.kind) {
    case "v0":
      return <>{children}</>;
    case "redirect":
      return <Navigate to={resolution.to} replace />;
    case "v1":
      return <V1Root entry={resolution.entry} />;
  }
}
