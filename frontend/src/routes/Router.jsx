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
import { useMainAppRoutes } from "./useMainAppRoutes.js";

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
