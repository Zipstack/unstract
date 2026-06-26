import { Button, Result } from "antd";
import { Suspense } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { GenericLoader } from "../../generic-loader/GenericLoader.jsx";
import { ErrorBoundary } from "../../widgets/error-boundary/ErrorBoundary.jsx";

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
      fallbackComponent={<RouteLoadError />}
    >
      <Suspense fallback={<GenericLoader />}>
        <Outlet />
      </Suspense>
    </ErrorBoundary>
  );
}
