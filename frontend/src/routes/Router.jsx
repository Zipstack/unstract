import { setOldVersion, VersionSwitch, v1DevRoutesEnabled } from "@v1";
import { Suspense } from "react";
import { Route, Routes, useLocation, useParams } from "react-router-dom";

import { GenericError } from "../components/error/GenericError/GenericError.jsx";
import {
  handleRouteError,
  RouteLoadError,
} from "../components/error/LazyOutlet/LazyOutlet.jsx";
import { NotFound } from "../components/error/NotFound/NotFound.jsx";
import { GenericLoader } from "../components/generic-loader/GenericLoader.jsx";
import { PersistentLogin } from "../components/helpers/auth/PersistentLogin.jsx";
import { RequireAuth } from "../components/helpers/auth/RequireAuth.jsx";
import { RequireGuest } from "../components/helpers/auth/RequireGuest.jsx";
import { OAuthStatus } from "../components/oauth-ds/oauth-status/OAuthStatus.jsx";
import { ErrorBoundary } from "../components/widgets/error-boundary/ErrorBoundary.jsx";
import { lazyNamed } from "../helpers/lazyNamed.js";
import { isModuleMissing } from "../helpers/pluginLoader.js";
import { lazyPlugin } from "../helpers/pluginRegistry.js";
import { LandingPage } from "../pages/LandingPage.jsx";
import { useSessionStore } from "../store/session-store.js";
import { useMainAppRoutes } from "./useMainAppRoutes.jsx";

// Heavy route pages are code-split so the unauthenticated /landing page does
// not download their chunks (PDF viewer, Monaco, charts) before login. The
// single <Suspense> boundary below covers these as well as the lazy pages
// rendered by useMainAppRoutes (they share this <Routes>).
const OutputAnalyzerPage = lazyNamed(
  () => import("../pages/OutputAnalyzerPage.jsx"),
  "OutputAnalyzerPage",
);
const SetOrgPage = lazyNamed(
  () => import("../pages/SetOrgPage.jsx"),
  "SetOrgPage",
);
const ToolIdePage = lazyNamed(
  () => import("../pages/ToolIdePage.jsx"),
  "ToolIdePage",
);

// Enterprise plugin route elements are code-split (see lazyPlugin). Each
// returns a React.lazy component whose chunk loads only on navigation — so
// none are fetched on the unauthenticated /landing page. In OSS the import
// resolves to a stub and the element falls back to NotFound, so these routes
// harmlessly 404 instead of crashing. The `{Component && <Route/>}` guards
// below are retained but are always truthy with this pattern.

// Marketplace buyer pages must be reachable at TOP-LEVEL paths: Tackle's
// post-purchase redirect is one static URL per environment
// (https://<env>/marketplace-landing?...) and cannot carry a per-buyer
// :orgName segment. The org-scoped variants under :orgName remain
// registered in useMainAppRoutes for in-app navigation; these top-level
// routes are the marketplace entry points. The landing page handles its
// own auth (redirects unauthenticated buyers through signup preserving
// the query params), so they sit outside RequireAuth.
const MarketplaceLandingEntry = lazyPlugin(
  () => import("../plugins/marketplace"),
  "MarketplaceLandingPage",
);
const MarketplaceStripeConflictEntry = lazyPlugin(
  () => import("../plugins/marketplace"),
  "MarketplaceStripeConflictPage",
);
// LLMWhisperer buyers get their own entry point: the LLMWhisperer Tackle
// listings redirect here, and the page claims against the LLMWhisperer portal
// backend (a different endpoint than the Unstract claim) — routing them to
// /marketplace-landing would fire the Unstract claim instead.
const LlmWhispererMarketplaceLandingEntry = lazyPlugin(
  () => import("../plugins/llm-whisperer/pages/MarketplaceLandingPage.jsx"),
  "MarketplaceLandingPage",
);

// Simple Prompt Studio pages.
const SimplePromptStudioHelper = lazyPlugin(
  () => import("../plugins/simple-prompt-studio/SimplePromptStudioHelper.jsx"),
  "SimplePromptStudioHelper",
);
const SimplePromptStudio = lazyPlugin(
  () => import("../plugins/simple-prompt-studio/SimplePromptStudio.jsx"),
  "SimplePromptStudio",
);
const SpsLanding = lazyPlugin(
  () => import("../plugins/simple-prompt-studio/SpsLanding.jsx"),
  "SpsLanding",
);
const SpsUpload = lazyPlugin(
  () => import("../plugins/simple-prompt-studio/SpsUpload.jsx"),
  "SpsUpload",
);
const PublicPromptStudioHelper = lazyPlugin(
  () =>
    import(
      "../plugins/prompt-studio-public-share/helpers/PublicPromptStudioHelper.js"
    ),
  "PublicPromptStudioHelper",
);
const SelectProduct = lazyPlugin(
  () => import("../plugins/select-product/SelectProduct.jsx"),
  "SelectProduct",
);
// `/flow` on a deployment that does not serve Flow (UN-4669). nginx hands the
// path to the SPA (`try_files $uri /index.html`), so without a route the
// visitor got the bare `NotFound` below — a 404 that says nothing about Flow
// and offers nothing. The plugin explains it and points at the products this
// deployment does have.
//
// Absent in OSS, where `lazyPlugin` resolves to a stub and the element falls
// back to `NotFound` — correct there, since an OSS build has no Flow at all.
const FlowUnavailable = lazyPlugin(
  () => import("../plugins/flow-unavailable/FlowUnavailable.jsx"),
  "FlowUnavailable",
);
const UnstractSubscriptionEndPage = lazyPlugin(
  () =>
    import(
      "../plugins/unstract-subscription/pages/UnstractSubscriptionEndPage.jsx"
    ),
  "UnstractSubscriptionEndPage",
);
const CustomPlanCheckoutPage = lazyPlugin(
  () =>
    import("../plugins/unstract-subscription/pages/CustomPlanCheckoutPage.jsx"),
  "CustomPlanCheckoutPage",
);
const PaymentSuccessful = lazyPlugin(
  () => import("../plugins/payment-successful/PaymentSuccessful.jsx"),
  "PaymentSuccessful",
);
const LlmWhispererCustomCheckoutPage = lazyPlugin(
  () =>
    import("../plugins/llm-whisperer/pages/LlmWhispererCustomCheckoutPage.jsx"),
  "LlmWhispererCustomCheckoutPage",
);

// These plugins export hooks that RETURN a <Route> tree consumed
// synchronously during render, so they cannot be wrapped in React.lazy and
// are loaded with a guarded await. OSS resolves these to the stub (caught
// below); cloud loads them. NOTE: in cloud these two modules still load on
// /landing because the await runs at module evaluation. Fully deferring them
// requires the plugins themselves (in unstract-cloud) to lazy-load their own
// page imports — tracked as a follow-up.
let llmWhispererRouter;
try {
  const mod = await import("../plugins/routes/useLlmWhispererRoutes.js");
  llmWhispererRouter = mod.useLlmWhispererRoutes;
} catch (err) {
  if (!isModuleMissing(err)) {
    console.error("[llm-whisperer] routes import failed unexpectedly", err);
  }
}

let verticalsRouter;
try {
  const mod = await import("../plugins/routes/useVerticalsRoutes.js");
  verticalsRouter = mod.useVerticalsRoutes;
} catch (err) {
  if (!isModuleMissing(err)) {
    console.error("[verticals] routes import failed unexpectedly", err);
  }
}

// Stand-ins for the v0 side of the v1 demo pages (UN-4271), which prove the
// version switch; routed only in a build with VITE_V1_DEV_ROUTES=true. The
// demo page is always live there, so V0DemoPage renders only if the switch
// fails to redirect: P0-T09's E2E specs (UN-4345, #2355) check for it, so it
// is not dead code.
function V0DemoPage() {
  return <h1 data-testid="v0-demo">v0 demo page</h1>;
}

function V0DemoReviewPage() {
  const { orgName } = useParams();
  return (
    <div data-testid="v0-demo-review">
      <h1>v0 demo review</h1>
      <p>{orgName}</p>
      <button type="button" onClick={() => setOldVersion(false)}>
        Switch to new version
      </button>
    </div>
  );
}

function Router() {
  const location = useLocation();
  const MainAppRoute = useMainAppRoutes();
  const userId = useSessionStore((state) => state.sessionDetails?.id);
  return (
    // Renders v1 for a URL whose page is live in the v1 route registry,
    // and these v0 routes for everything else (UN-4271).
    <VersionSwitch userId={userId}>
      {/* v0-wide backstop (the v1 tree has its own, in VersionSwitch):
          catches shell-level chunk failures and errors on routes that don't
          sit inside a LazyOutlet layout. Per-page load
          errors are handled by the scoped boundaries inside the layouts.
          resetKeys lets navigation clear the error without a full reload. */}
      <ErrorBoundary
        resetKeys={[location.pathname]}
        onError={handleRouteError}
        fallbackComponent={<RouteLoadError />}
      >
        <Suspense fallback={<GenericLoader />}>
          <Routes>
            <Route path="error" element={<GenericError />} />
            <Route path="" element={<PersistentLogin />}>
              {/* public routes */}
              <Route path="">
                {/* public routes accessible only to unauthenticated users */}
                <Route path="" element={<RequireGuest />}>
                  <Route path="landing" element={<LandingPage />} />
                </Route>

                {/* public routes accessible to both authenticated and unauthenticated users */}
                {SimplePromptStudioHelper &&
                  SimplePromptStudio &&
                  SpsLanding &&
                  SpsUpload && (
                    <Route
                      path="simple-prompt-studio"
                      element={<SimplePromptStudioHelper />}
                    >
                      <Route path="" element={<SimplePromptStudio />} />
                      <Route path="landing" element={<SpsLanding />} />
                      <Route path="upload" element={<SpsUpload />} />
                    </Route>
                  )}
                {PublicPromptStudioHelper && (
                  <Route
                    path="/promptStudio/share/:id"
                    element={<PublicPromptStudioHelper />}
                  >
                    <Route path="" element={<ToolIdePage />} />
                    <Route
                      path="/promptStudio/share/:id/outputAnalyzer"
                      element={<OutputAnalyzerPage />}
                    />
                  </Route>
                )}
              </Route>

              {/* protected routes */}
              <Route path="setOrg" element={<SetOrgPage />} />
              {SelectProduct && (
                <Route path="selectProduct" element={<SelectProduct />} />
              )}
              {UnstractSubscriptionEndPage && (
                <Route
                  path="/subscription-expired"
                  element={<UnstractSubscriptionEndPage />}
                />
              )}
              {PaymentSuccessful && (
                <Route
                  path="/payment/success"
                  element={<PaymentSuccessful />}
                />
              )}
              {MarketplaceLandingEntry && (
                <Route
                  path="/marketplace-landing"
                  element={<MarketplaceLandingEntry />}
                />
              )}
              {MarketplaceStripeConflictEntry && (
                <Route
                  path="/marketplace-stripe-conflict"
                  element={<MarketplaceStripeConflictEntry />}
                />
              )}
              {LlmWhispererMarketplaceLandingEntry && (
                <Route
                  path="/llm-whisperer/marketplace-landing"
                  element={<LlmWhispererMarketplaceLandingEntry />}
                />
              )}
              {CustomPlanCheckoutPage && (
                <Route
                  path="/subscription/custom"
                  element={<CustomPlanCheckoutPage />}
                />
              )}
              {LlmWhispererCustomCheckoutPage && (
                <Route
                  path="/llm-whisperer/custom-checkout"
                  element={<LlmWhispererCustomCheckoutPage />}
                />
              )}
              <Route path="" element={<RequireAuth />}>
                {MainAppRoute}
                {llmWhispererRouter && (
                  <Route path="llm-whisperer">{llmWhispererRouter()}</Route>
                )}
                {v1DevRoutesEnabled && (
                  <>
                    <Route path=":orgName/v0-demo" element={<V0DemoPage />} />
                    <Route
                      path=":orgName/v0-demo-review"
                      element={<V0DemoReviewPage />}
                    />
                  </>
                )}
              </Route>
              {verticalsRouter && verticalsRouter()}
            </Route>
            {FlowUnavailable && (
              <Route path="flow/*" element={<FlowUnavailable />} />
            )}
            <Route path="*" element={<NotFound />} />
            <Route path="oauth-status" element={<OAuthStatus />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </VersionSwitch>
  );
}

export { Router };
