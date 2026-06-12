import { Route, Routes } from "react-router-dom";

import { GenericError } from "../components/error/GenericError/GenericError.jsx";
import { NotFound } from "../components/error/NotFound/NotFound.jsx";
import { PersistentLogin } from "../components/helpers/auth/PersistentLogin.js";
import { RequireAuth } from "../components/helpers/auth/RequireAuth.js";
import { RequireGuest } from "../components/helpers/auth/RequireGuest.js";
import { OAuthStatus } from "../components/oauth-ds/oauth-status/OAuthStatus.jsx";
import { LandingPage } from "../pages/LandingPage.jsx";
import { OutputAnalyzerPage } from "../pages/OutputAnalyzerPage.jsx";
import { SetOrgPage } from "../pages/SetOrgPage.jsx";
import { ToolIdePage } from "../pages/ToolIdePage.jsx";
import { isModuleMissing, useMainAppRoutes } from "./useMainAppRoutes.js";

// Marketplace buyer pages must be reachable at TOP-LEVEL paths: Tackle's
// post-purchase redirect is one static URL per environment
// (https://<env>/marketplace-landing?...) and cannot carry a per-buyer
// :orgName segment. The org-scoped variants under :orgName remain
// registered in useMainAppRoutes for in-app navigation; these top-level
// routes are the marketplace entry points. The landing page handles its
// own auth (redirects unauthenticated buyers through signup preserving
// the query params), so they sit outside RequireAuth.
let MarketplaceLandingEntry;
let MarketplaceStripeConflictEntry;
try {
  const marketplaceMod = await import("../plugins/marketplace");
  MarketplaceLandingEntry = marketplaceMod.MarketplaceLandingPage;
  MarketplaceStripeConflictEntry = marketplaceMod.MarketplaceStripeConflictPage;
} catch (err) {
  // Expected in OSS builds where the cloud plugin is absent.
  if (!isModuleMissing(err)) {
    // eslint-disable-next-line no-console
    console.error(
      "[marketplace] Plugin import failed unexpectedly; marketplace " +
        "entry routes disabled",
      err,
    );
  }
}

let PublicPromptStudioHelper;

// Import pages/components related to Simple Prompt Studio.
let SimplePromptStudioHelper;
let SimplePromptStudio;
let SpsLanding;
let SpsUpload;
let PaymentSuccessful;
let SelectProduct;
let UnstractSubscriptionEndPage;
let CustomPlanCheckoutPage;
try {
  const spsHelperMod = await import(
    "../plugins/simple-prompt-studio/SimplePromptStudioHelper.jsx"
  );
  SimplePromptStudioHelper = spsHelperMod.SimplePromptStudioHelper;
  const spsMod = await import(
    "../plugins/simple-prompt-studio/SimplePromptStudio.jsx"
  );
  SimplePromptStudio = spsMod.SimplePromptStudio;
  const spsLandingMod = await import(
    "../plugins/simple-prompt-studio/SpsLanding.jsx"
  );
  SpsLanding = spsLandingMod.SpsLanding;
  const spsUploadMod = await import(
    "../plugins/simple-prompt-studio/SpsUpload.jsx"
  );
  SpsUpload = spsUploadMod.SpsUpload;
} catch {
  // Do nothing, Not-found Page will be triggered.
}
try {
  const mod = await import(
    "../plugins/prompt-studio-public-share/helpers/PublicPromptStudioHelper.js"
  );
  PublicPromptStudioHelper = mod.PublicPromptStudioHelper;
} catch {
  // Do nothing, Not-found Page will be triggered.
}

let llmWhispererRouter;
try {
  const mod = await import("../plugins/routes/useLlmWhispererRoutes.js");
  llmWhispererRouter = mod.useLlmWhispererRoutes;
} catch {
  // Do nothing, Not-found Page will be triggered.
}

let verticalsRouter;
try {
  const mod = await import("../plugins/routes/useVerticalsRoutes.js");
  verticalsRouter = mod.useVerticalsRoutes;
} catch {
  // Do nothing, Not-found Page will be triggered.
}

try {
  const mod = await import("../plugins/select-product/SelectProduct.jsx");
  SelectProduct = mod.SelectProduct;
} catch {
  // Do nothing, Not-found Page will be triggered.
}

try {
  const mod = await import(
    "../plugins/unstract-subscription/pages/UnstractSubscriptionEndPage.jsx"
  );
  UnstractSubscriptionEndPage = mod.UnstractSubscriptionEndPage;
} catch {
  // Do nothing, Not-found Page will be triggered.
}

try {
  const mod = await import(
    "../plugins/unstract-subscription/pages/CustomPlanCheckoutPage.jsx"
  );
  CustomPlanCheckoutPage = mod.CustomPlanCheckoutPage;
} catch {
  // Do nothing, Not-found Page will be triggered.
}

try {
  const mod = await import(
    "../plugins/payment-successful/PaymentSuccessful.jsx"
  );
  PaymentSuccessful = mod.PaymentSuccessful;
} catch {
  // Do nothing, Not-found Page will be triggered.
}

let LlmWhispererCustomCheckoutPage;
try {
  const mod = await import(
    "../plugins/llm-whisperer/pages/LlmWhispererCustomCheckoutPage.jsx"
  );
  LlmWhispererCustomCheckoutPage = mod.LlmWhispererCustomCheckoutPage;
} catch {
  // NOSONAR
  // Do nothing, Not-found Page will be triggered.
}

function Router() {
  const MainAppRoute = useMainAppRoutes();
  return (
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
  );
}

export { Router };
