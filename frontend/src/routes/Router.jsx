import { Route, Routes } from "react-router-dom";

import { GenericError } from "../components/error/GenericError/GenericError.jsx";
import { NotFound } from "../components/error/NotFound/NotFound.jsx";
import { PersistentLogin } from "../components/helpers/auth/PersistentLogin.js";
import { RequireAdmin } from "../components/helpers/auth/RequireAdmin.js";
import { RequireAuth } from "../components/helpers/auth/RequireAuth.js";
import { RequireGuest } from "../components/helpers/auth/RequireGuest.js";
import { CustomToolsHelper } from "../components/helpers/custom-tools/CustomToolsHelper.js";
import { ProjectHelper } from "../components/helpers/project/ProjectHelper.js";
import { OAuthStatus } from "../components/oauth-ds/oauth-status/OAuthStatus.jsx";
import { DefaultTriad } from "../components/settings/default-triad/DefaultTriad.jsx";
import { PlatformSettings } from "../components/settings/platform/PlatformSettings.jsx";
import { deploymentTypes } from "../helpers/GetStaticData.js";
import { FullPageLayout } from "../layouts/fullpage-payout/FullPageLayout.jsx";
import { PageLayout } from "../layouts/page-layout/PageLayout.jsx";
import { AgencyPage } from "../pages/AgencyPage.jsx";
import { CustomTools } from "../pages/CustomTools.jsx";
import { DeploymentsPage } from "../pages/DeploymentsPage.jsx";
import { InviteEditUserPage } from "../pages/InviteEditUserPage.jsx";
import { LandingPage } from "../pages/LandingPage.jsx";
import { OnBoardPage } from "../pages/OnBoardPage.jsx";
import { OutputAnalyzerPage } from "../pages/OutputAnalyzerPage.jsx";
import { ProfilePage } from "../pages/ProfilePage.jsx";
import { SetOrgPage } from "../pages/SetOrgPage.jsx";
import { SettingsPage } from "../pages/SettingsPage.jsx";
import { ToolIdePage } from "../pages/ToolIdePage.jsx";
import { ToolsSettingsPage } from "../pages/ToolsSettingsPage.jsx";
import { UsersPage } from "../pages/UsersPage.jsx";
import { WorkflowsPage } from "../pages/WorkflowsPage.jsx";

let TrialRoutes;
let RequirePlatformAdmin;
let PlatformAdminPage;
let AppDeployments;
let ChatAppPage;
let ChatAppLayout;
let ManualReviewPage;
let ReviewLayout;
try {
  TrialRoutes =
    require("../plugins/subscription/trial-page/TrialEndPage.jsx").TrialEndPage;
  RequirePlatformAdmin =
    require("../plugins/frictionless-onboard/RequirePlatformAdmin.jsx").RequirePlatformAdmin;
  PlatformAdminPage =
    require("../plugins/frictionless-onboard/platform-admin-page/PlatformAdminPage.jsx").PlatformAdminPage;
} catch (err) {
  // Do nothing, Not-found Page will be triggered.
}

try {
  AppDeployments =
    require("../plugins/app-deployment/AppDeployments.jsx").AppDeployments;
  ChatAppPage =
    require("../plugins/app-deployment/chat-app/ChatAppPage.jsx").ChatAppPage;
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
        <Route path="" element={<RequireAuth />}>
          <Route path=":orgName" element={<FullPageLayout />}>
            <Route path="onboard" element={<OnBoardPage />} />
          </Route>
          {ChatAppLayout && ChatAppPage && (
            <Route path=":orgName" element={<ChatAppLayout />}>
              <Route path="app/:id" element={<ChatAppPage />} />
            </Route>
          )}
          <Route path=":orgName" element={<PageLayout />}>
            <Route path="profile" element={<ProfilePage />} />
            <Route
              path="api"
              element={<DeploymentsPage type={deploymentTypes.api} />}
            />
            <Route
              path="etl"
              element={<DeploymentsPage type={deploymentTypes.etl} />}
            />
            <Route
              path="task"
              element={<DeploymentsPage type={deploymentTypes.task} />}
            />
            {AppDeployments && (
              <Route path="app" element={<AppDeployments type="app" />} />
            )}
            <Route path="workflows" element={<WorkflowsPage />} />
            <Route path="workflows/:id" element={<ProjectHelper />}>
              <Route path="" element={<AgencyPage />} />
            </Route>
            <Route path="tools" element={<CustomTools />} />
            <Route path="" element={<CustomToolsHelper />}>
              <Route path="tools/:id" element={<ToolIdePage />} />
              <Route
                path="tools/:id/outputAnalyzer"
                element={<OutputAnalyzerPage />}
              />
            </Route>
            <Route
              path="settings/llms"
              element={<ToolsSettingsPage type="llm" />}
            />
            <Route
              path="settings/vectorDbs"
              element={<ToolsSettingsPage type="vector_db" />}
            />
            <Route
              path="settings/embedding"
              element={<ToolsSettingsPage type="embedding" />}
            />
            <Route
              path="settings/textExtractor"
              element={<ToolsSettingsPage type="x2text" />}
            />
            <Route
              path="settings/ocr"
              element={<ToolsSettingsPage type="ocr" />}
            />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="settings/platform" element={<PlatformSettings />} />
            <Route element={<RequireAdmin />}>
              <Route path="users" element={<UsersPage />} />
              <Route path="users/invite" element={<InviteEditUserPage />} />
              <Route path="users/edit" element={<InviteEditUserPage />} />
            </Route>
            <Route path="settings/triad" element={<DefaultTriad />} />
            {RequirePlatformAdmin && PlatformAdminPage && (
              <Route element={<RequirePlatformAdmin />}>
                <Route path="settings/admin" element={<PlatformAdminPage />} />
              </Route>
            )}
          </Route>
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
    </Routes>
  );
}

export { Router };
