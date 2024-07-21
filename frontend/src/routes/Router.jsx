import { Route, Routes } from "react-router-dom";

import { GenericError } from "../components/error/GenericError/GenericError.jsx";
import { NotFound } from "../components/error/NotFound/NotFound.jsx";
import { PersistentLogin } from "../components/helpers/auth/PersistentLogin.js";
import { RequireGuest } from "../components/helpers/auth/RequireGuest.js";
import { OAuthStatus } from "../components/oauth-ds/oauth-status/OAuthStatus.jsx";
import { LandingPage } from "../pages/LandingPage.jsx";
import { SetOrgPage } from "../pages/SetOrgPage.jsx";
import { useMainAppRoutes } from "./useMainAppRoutes.js";
import { useLlmWhispererRoutes } from "../plugins/routes/useLlmWhispererRoutes.js";
import { RequireAuth } from "../components/helpers/auth/RequireAuth.js";
import { SelectProduct } from "../plugins/select-product/SelectProduct.jsx";

let TrialRoutes;
let ManualReviewPage;
let ReviewLayout;
try {
  TrialRoutes =
    require("../plugins/subscription/trial-page/TrialEndPage.jsx").TrialEndPage;
} catch (err) {
  // Do nothing, Not-found Page will be triggered.
}

try {
  ManualReviewPage =
    require("../plugins/manual-review/page/ManualReviewPage.jsx").ManualReviewPage;
  ReviewLayout =
    require("../plugins/manual-review/review-layout/ReviewLayout.jsx").ReviewLayout;
} catch (err) {
  // Do nothing, Not-found Page will be triggered.
}
// Import pages/components related to Simple Prompt Studio.
let SimplePromptStudioHelper;
let SimplePromptStudio;
let SpsLanding;
let SpsUpload;
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

function Router() {
  const MainAppRoute = useMainAppRoutes();
  const LlmWhispererRoutes = useLlmWhispererRoutes();
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
        </Route>

        {/* protected routes */}
        <Route path="setOrg" element={<SetOrgPage />} />
        <Route path="">{MainAppRoute}</Route>
        <Route path="llm-whisperer">{LlmWhispererRoutes}</Route>
        <Route path="" element={<RequireAuth />}>
          {ReviewLayout && ManualReviewPage && (
            <Route path=":orgName" element={<ReviewLayout />}>
              <Route
                path="review"
                element={<ManualReviewPage type="review" />}
              ></Route>
              <Route
                path="review/download_and_sync"
                element={<ManualReviewPage type="download" />}
              />
              <Route
                path="review/approve"
                element={<ManualReviewPage type="approve" />}
              />
            </Route>
          )}
        </Route>
        {TrialRoutes && (
          <Route path="/trial-expired" element={<TrialRoutes />} />
        )}
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route path="oauth-status" element={<OAuthStatus />} />
      <Route path="selectProduct" element={<SelectProduct />} />
    </Routes>
  );
}

export { Router };
