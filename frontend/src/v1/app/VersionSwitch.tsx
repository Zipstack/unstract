/*
 * The version switch (UN-4271): renders v0 or v1 per URL. v0's router mounts
 * it around its own routes, as `children`, which render untouched whenever
 * the URL resolves to v0.
 */

import { LIVE_REGISTRY, type LiveRegistry } from "@v1/app/registry/live";
import { resolveRoute } from "@v1/app/registry/resolve";
import type { RegistryEntry } from "@v1/app/registry/types";
import { V1ErrorBoundary } from "@v1/app/V1ErrorBoundary";
import { registerUiVersion, type UiVersion } from "@v1/lib/analytics";
import { useOldVersionStore } from "@v1/stores/oldVersion";
import {
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

/** The signed-in user's old-version choice; null while unknown. */
function useOldVersionChoice(user: string | null): boolean | null {
  const storeUser = useOldVersionStore((s) => s.userId);
  const storedChoice = useOldVersionStore((s) => s.oldVersion);
  useLayoutEffect(() => {
    useOldVersionStore.getState().setUser(user);
  }, [user]);
  // Until the store has caught up with a newly signed-in user, their choice
  // is unknown, so the previous user's never redirects them.
  return user !== null && user !== storeUser ? null : storedChoice;
}

/** Tags events with the version on screen; a layout effect, so before v0's tracker (a passive effect) captures the page view. */
function useUiVersionTag(version: UiVersion): void {
  useLayoutEffect(() => {
    registerUiVersion(version);
  }, [version]);
}

export function VersionSwitch({
  userId,
  children,
  registry = LIVE_REGISTRY,
}: VersionSwitchProps): JSX.Element {
  const location = useLocation();
  const oldVersion = useOldVersionChoice(toUserId(userId));
  const resolution = resolveRoute(location, {
    entries: registry.entries,
    oldVersion,
  });
  useUiVersionTag(resolution.kind === "v1" ? "v1" : "v0");

  switch (resolution.kind) {
    case "v0":
      return <>{children}</>;
    case "redirect":
      return <Navigate to={resolution.to} replace />;
    case "v1":
      return <V1Root entry={resolution.entry} pathname={location.pathname} />;
  }
}
