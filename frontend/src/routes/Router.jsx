import { Outlet, Route, Routes } from "react-router-dom";

import { GenericError } from "../components/error/GenericError/GenericError.jsx";
import { NotFound } from "../components/error/NotFound/NotFound.jsx";
import { PersistentLogin } from "../components/helpers/auth/PersistentLogin.js";
import { RequireGuest } from "../components/helpers/auth/RequireGuest.js";
import { OAuthStatus } from "../components/oauth-ds/oauth-status/OAuthStatus.jsx";
import { LandingPage } from "../pages/LandingPage.jsx";
import { SetOrgPage } from "../pages/SetOrgPage.jsx";
import { useMainAppRoutes } from "./useMainAppRoutes.js";
import { RequireAuth } from "../components/helpers/auth/RequireAuth.js";
import { ToolIdePage } from "../pages/ToolIdePage.jsx";
import { OutputAnalyzerPage } from "../pages/OutputAnalyzerPage.jsx";

let PublicPromptStudioHelper;

// Import pages/components related to Simple Prompt Studio.
let SimplePromptStudioHelper;
let SimplePromptStudio;
let SpsLanding;
let SpsUpload;
let PaymentSuccessful;
let SelectProduct;
let UnstractSubscriptionCheck;
let UnstractSubscriptionEndPage;
try {
  SimplePromptStudioHelper =
    require("../plugins/simple-prompt-studio/SimplePromptStudioHelper.jsx").SimplePromptStudioHelper;
  SimplePromptStudio =
    require("../plugins/simple-prompt-studio/SimplePromptStudio.jsx").SimplePromptStudio;
  SpsLanding =
    require("../plugins/simple-prompt-studio/SpsLanding.jsx").SpsLanding;
  SpsUpload =
    require("../plugins/simple-prompt-studio/SpsUpload.jsx").SpsUpload;
} catch (err) {
  // Do nothing, Not-found Page will be triggered.
}
try {
  PublicPromptStudioHelper =
    require("../plugins/prompt-studio-public-share/helpers/PublicPromptStudioHelper.js").PublicPromptStudioHelper;
} catch (err) {
  // Do nothing, Not-found Page will be triggered.
}

let llmWhispererRouter;
try {
  llmWhispererRouter =
    require("../plugins/routes/useLlmWhispererRoutes.js").useLlmWhispererRoutes;
} catch (err) {
  // Do nothing, Not-found Page will be triggered.
}

try {
  SelectProduct =
    require("../plugins/select-product/SelectProduct.jsx").SelectProduct;
} catch (err) {
  // Do nothing, Not-found Page will be triggered.
}

try {
  UnstractSubscriptionEndPage =
    require("../plugins/unstract-subscription/pages/UnstractSubscriptionEndPage.jsx").UnstractSubscriptionEndPage;
} catch (err) {
  // Do nothing, Not-found Page will be triggered.
}

try {
  PaymentSuccessful =
    require("../plugins/payment-successful/PaymentSuccessful.jsx").PaymentSuccessful;
} catch (err) {
  // Do nothing, Not-found Page will be triggered.
}

try {
  UnstractSubscriptionCheck =
    require("../plugins/unstract-subscription/components/UnstractSubscriptionCheck.jsx").UnstractSubscriptionCheck;
} catch (err) {
  // Do nothing.
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
        <Route path="" element={<RequireAuth />}>
          <Route
            path=""
            element={
              UnstractSubscriptionCheck ? (
                <UnstractSubscriptionCheck />
              ) : (
                <Outlet />
              )
            }
          >
            {MainAppRoute}
          </Route>
          {llmWhispererRouter && (
            <Route path="llm-whisperer">{llmWhispererRouter()}</Route>
          )}
        </Route>
      </Route>

      <Route path="*" element={<NotFound />} />
      <Route path="oauth-status" element={<OAuthStatus />} />
    </Routes>
  );
}

export { Router };
