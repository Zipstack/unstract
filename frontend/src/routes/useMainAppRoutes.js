import { Route } from "react-router-dom";

import { OnBoardPage } from "../pages/OnBoardPage.jsx";
import { FullPageLayout } from "../layouts/fullpage-payout/FullPageLayout.jsx";
import { ToolsSettingsPage } from "../pages/ToolsSettingsPage.jsx";
import { SettingsPage } from "../pages/SettingsPage.jsx";
import { PlatformSettings } from "../components/settings/platform/PlatformSettings.jsx";
import { RequireAdmin } from "../components/helpers/auth/RequireAdmin.js";
import { UsersPage } from "../pages/UsersPage.jsx";
import { InviteEditUserPage } from "../pages/InviteEditUserPage.jsx";
import { DefaultTriad } from "../components/settings/default-triad/DefaultTriad.jsx";
import { PageLayout } from "../layouts/page-layout/PageLayout.jsx";
import { ProfilePage } from "../pages/ProfilePage.jsx";
import { DeploymentsPage } from "../pages/DeploymentsPage.jsx";
import { WorkflowsPage } from "../pages/WorkflowsPage.jsx";
import { ProjectHelper } from "../components/helpers/project/ProjectHelper.js";
import { AgencyPage } from "../pages/AgencyPage.jsx";
import { CustomTools } from "../pages/CustomTools.jsx";
import { CustomToolsHelper } from "../components/helpers/custom-tools/CustomToolsHelper.js";
import { ToolIdePage } from "../pages/ToolIdePage.jsx";
import { OutputAnalyzerPage } from "../pages/OutputAnalyzerPage.jsx";
import { deploymentTypes } from "../helpers/GetStaticData.js";
import { RequireAuth } from "../components/helpers/auth/RequireAuth.js";

let RequirePlatformAdmin;
let PlatformAdminPage;
let AppDeployments;
let ChatAppPage;
let ChatAppLayout;
let ManualReviewSettings;

try {
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
  ChatAppLayout =
    require("../plugins/app-deployment/chat-app/ChatAppLayout.jsx").ChatAppLayout;
} catch (err) {
  // Do nothing, Not-found Page will be triggered.
}

try {
  ManualReviewSettings =
    require("../plugins/manual-review/settings/Settings.jsx").ManualReviewSettings;
} catch (err) {
  // Do nothing, Not-found Page will be triggered.
}

function useMainAppRoutes() {
  return (
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
        <Route path="settings/ocr" element={<ToolsSettingsPage type="ocr" />} />
        <Route path="settings" element={<SettingsPage />} />
        {ManualReviewSettings && (
          <Route path="settings/review" element={<ManualReviewSettings />} />
        )}
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
    </Route>
  );
}

export { useMainAppRoutes };
