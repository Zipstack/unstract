import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

import { GenericError } from "../components/error/GenericError/GenericError.jsx";
import { NotFound } from "../components/error/NotFound/NotFound.jsx";
import { GenericLoader } from "../components/generic-loader/GenericLoader.jsx";
import { PersistentLogin } from "../components/helpers/auth/PersistentLogin.js";
import { RequireAuth } from "../components/helpers/auth/RequireAuth.js";
import { RequireGuest } from "../components/helpers/auth/RequireGuest.js";
import { OAuthStatus } from "../components/oauth-ds/oauth-status/OAuthStatus.jsx";
import { isModuleMissing } from "../helpers/pluginLoader.js";
import { lazyPlugin } from "../helpers/pluginRegistry.js";
import { LandingPage } from "../pages/LandingPage.jsx";
import { useMainAppRoutes } from "./useMainAppRoutes.js";

// Heavy route pages are code-split so the unauthenticated /landing page does
// not download their chunks (PDF viewer, Monaco, charts) before login. The
// single <Suspense> boundary below covers these as well as the lazy pages
// rendered by useMainAppRoutes (they share this <Routes>).
const OutputAnalyzerPage = lazy(() =>
  import("../pages/OutputAnalyzerPage.jsx").then((m) => ({
    default: m.OutputAnalyzerPage,
  })),
);
const SetOrgPage = lazy(() =>
  import("../pages/SetOrgPage.jsx").then((m) => ({ default: m.SetOrgPage })),
);
const ToolIdePage = lazy(() =>
  import("../pages/ToolIdePage.jsx").then((m) => ({ default: m.ToolIdePage })),
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
    // eslint-disable-next-line no-console
    console.error("[llm-whisperer] routes import failed unexpectedly", err);
  }
}

let verticalsRouter;
try {
  const mod = await import("../plugins/routes/useVerticalsRoutes.js");
  verticalsRouter = mod.useVerticalsRoutes;
} catch (err) {
  if (!isModuleMissing(err)) {
    // eslint-disable-next-line no-console
    console.error("[verticals] routes import failed unexpectedly", err);
  }
}

function Router() {
  const MainAppRoute = useMainAppRoutes();
  return (
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
            <Route path="/payment/success" element={<PaymentSuccessful />} />
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
          </Route>
          {verticalsRouter && verticalsRouter()}
        </Route>
        <Route path="*" element={<NotFound />} />
        <Route path="oauth-status" element={<OAuthStatus />} />
      </Routes>
    </Suspense>
  );
}

export { Router };
