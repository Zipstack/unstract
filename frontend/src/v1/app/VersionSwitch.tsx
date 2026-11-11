/*
 * The version switch (UN-4271): renders v0 or v1 per URL. v0's router mounts
 * it around its own routes, as `children`, which render untouched whenever
 * the URL resolves to v0.
 */

import { LIVE_REGISTRY, type LiveRegistry } from "@v1/app/registry/live";
import { resolveRoute } from "@v1/app/registry/resolve";
import type { RegistryEntry } from "@v1/app/registry/types";
import { isChunkLoadError, reloadOnce } from "@v1/lib/chunkReload";
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

function sessionStore(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/**
 * Keeps a v1 failure from unmounting the whole app. A stale chunk after a
 * deploy reloads the page once to fetch the new one (React caches a failed
 * lazy import, so nothing short of a reload retries it); anything else, or a
 * repeat failure, shows the fallback. Navigating to another URL clears it, as
 * v0's backstop does with `resetKeys`.
 */
class V1ErrorBoundary extends Component<
  { children: ReactNode; resetKey: string },
  BoundaryState
> {
  override state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  override componentDidUpdate(prev: Readonly<{ resetKey: string }>): void {
    if (this.state.failed && prev.resetKey !== this.props.resetKey) {
      this.setState({ failed: false });
    }
  }

  override componentDidCatch(error: unknown): void {
    if (isChunkLoadError(error)) {
      reloadOnce(sessionStore(), () => window.location.reload());
    }
  }

  override render(): ReactNode {
    if (this.state.failed) {
      return (
        <div className="ui:p-6" role="alert">
          <p>This page could not be loaded.</p>
          <button type="button" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function V1Root({
  entry,
  pathname,
}: Readonly<{ entry: RegistryEntry; pathname: string }>): JSX.Element {
  // Keyed by page so another page starts clean; within a page, a new
  // pathname clears a failure without remounting the tree.
  return (
    <V1ErrorBoundary key={entry.page} resetKey={pathname}>
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
      return <V1Root entry={resolution.entry} pathname={location.pathname} />;
  }
}
