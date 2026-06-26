import { Button, Result } from "antd";
import { Suspense } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { GenericLoader } from "../../generic-loader/GenericLoader.jsx";
import { ErrorBoundary } from "../../widgets/error-boundary/ErrorBoundary.jsx";

// A failed dynamic import — almost always a stale hashed chunk after a
// redeploy (the client's index.html references a filename the CDN no longer
// serves). Matching is best-effort across browsers/bundlers.
export function isChunkLoadError(err) {
  const msg = err?.message || "";
  return (
    err?.name === "ChunkLoadError" ||
    msg.includes("Failed to fetch dynamically imported module") ||
    msg.includes("error loading dynamically imported module") ||
    msg.includes("Importing a module script failed")
  );
}

// onError handler for the route boundaries. On a chunk-load error, reload ONCE
// to pick up fresh chunk hashes from the new deploy. A timestamp guard prevents
// a reload loop when the chunk is genuinely gone: a repeat failure inside the
// window falls through to the manual "Reload" fallback instead. Non-chunk
// errors (real render bugs) are left for the fallback — never auto-reloaded.
export function handleRouteError({ error }) {
  if (!isChunkLoadError(error)) {
    return;
  }
  try {
    const KEY = "route-chunk-reload-ts";
    const last = Number(sessionStorage.getItem(KEY) || 0);
    if (Date.now() - last > 10000) {
      sessionStorage.setItem(KEY, String(Date.now()));
      globalThis.location.reload();
    }
  } catch {
    // sessionStorage unavailable (private mode, etc.) — skip the auto-reload
    // and let the manual fallback handle recovery.
  }
}

// Shown when a lazy route chunk fails to load (a transient network/CDN blip, or
// a stale hashed asset after a deploy). lazyPlugin/lazyNamed rethrow such
// failures; without a boundary React would unmount the tree to a blank screen.
// Reloading re-fetches the chunk, so that is the offered recovery.
export function RouteLoadError() {
  return (
    <Result
      status="warning"
      title="Couldn't load this page"
      subTitle="Part of the app failed to load — this is usually a temporary network issue. Reloading should fix it."
      extra={
        <Button type="primary" onClick={() => globalThis.location.reload()}>
          Reload
        </Button>
      }
    />
  );
}

// Renders the routed page (<Outlet/>) inside a CONTENT-SCOPED Suspense and a
// navigation-resettable ErrorBoundary. Use it inside a persistent layout in
// place of a bare <Outlet/> so the shell (sidebar/topnav) stays mounted:
// per-page load spinners and chunk-load failures are confined to the content
// area, and navigating away (the shell nav stays interactive) recovers without
// a full reload. The app-wide boundary in Router.jsx remains the backstop for
// shell-level failures and routes that don't use a layout.
export function LazyOutlet() {
  const location = useLocation();
  return (
    <ErrorBoundary
      resetKeys={[location.pathname]}
      onError={handleRouteError}
      fallbackComponent={<RouteLoadError />}
    >
      <Suspense fallback={<GenericLoader />}>
        <Outlet />
      </Suspense>
    </ErrorBoundary>
  );
}
