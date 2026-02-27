import { Route } from "react-router-dom";
import { RequireAdmin } from "../components/helpers/auth/RequireAdmin.js";
import { CustomToolsHelper } from "../components/helpers/custom-tools/CustomToolsHelper.js";
import { ProjectHelper } from "../components/helpers/project/ProjectHelper.js";
import { DefaultTriad } from "../components/settings/default-triad/DefaultTriad.jsx";
import { PlatformSettings } from "../components/settings/platform/PlatformSettings.jsx";
import { deploymentTypes } from "../helpers/GetStaticData.js";
import { FullPageLayout } from "../layouts/fullpage-payout/FullPageLayout.jsx";
import { PageLayout } from "../layouts/page-layout/PageLayout.jsx";
import { AgencyPage } from "../pages/AgencyPage.jsx";
import ConnectorsPage from "../pages/ConnectorsPage.jsx";
import { CustomTools } from "../pages/CustomTools.jsx";
import { DeploymentsPage } from "../pages/DeploymentsPage.jsx";
import { InviteEditUserPage } from "../pages/InviteEditUserPage.jsx";
import { LogsPage } from "../pages/LogsPage.jsx";
import { OnBoardPage } from "../pages/OnBoardPage.jsx";
import { OutputAnalyzerPage } from "../pages/OutputAnalyzerPage.jsx";
import { ProfilePage } from "../pages/ProfilePage.jsx";
import { SettingsPage } from "../pages/SettingsPage.jsx";
import { ToolIdePage } from "../pages/ToolIdePage.jsx";
import { ToolsSettingsPage } from "../pages/ToolsSettingsPage.jsx";
import { UnstractAdministrationPage } from "../pages/UnstractAdministrationPage.jsx";
import { UsersPage } from "../pages/UsersPage.jsx";
import { WorkflowsPage } from "../pages/WorkflowsPage.jsx";

let RequirePlatformAdmin;
let PlatformAdminPage;
let AppDeployments;
let ChatAppPage;
let ChatAppLayout;
let ManualReviewSettings;
let OnboardProduct;
let PRODUCT_NAMES = {};
let ManualReviewPage;
let SimpleManualReviewPage;
let ReviewLayout;
let Manage;
let UnstractUsagePage;
let UnstractSubscriptionPage;
let UnstractSubscriptionCheck;
let AgenticPromptStudio;

try {
  const mod1 = await import(
    "../plugins/frictionless-onboard/RequirePlatformAdmin.jsx"
  );
  RequirePlatformAdmin = mod1.RequirePlatformAdmin;
  const mod2 = await import(
    "../plugins/frictionless-onboard/platform-admin-page/PlatformAdminPage.jsx"
  );
  PlatformAdminPage = mod2.PlatformAdminPage;
} catch {
  // Do nothing, Not-found Page will be triggered.
}

try {
  const mod = await import("../plugins/agentic-prompt-studio");
  AgenticPromptStudio = mod.AgenticPromptStudio;
} catch {
  // Do nothing, Not-found Page will be triggered.
}

try {
  const mod1 = await import("../plugins/app-deployment/AppDeployments.jsx");
  AppDeployments = mod1.AppDeployments;
  const mod2 = await import(
    "../plugins/app-deployment/chat-app/ChatAppPage.jsx"
  );
  ChatAppPage = mod2.ChatAppPage;
  const mod3 = await import(
    "../plugins/app-deployment/chat-app/ChatAppLayout.jsx"
  );
  ChatAppLayout = mod3.ChatAppLayout;
} catch {
  // Do nothing, Not-found Page will be triggered.
}

try {
  const mod = await import("../plugins/manual-review/settings/Settings.jsx");
  ManualReviewSettings = mod.ManualReviewSettings;
} catch {
  // Do nothing, Not-found Page will be triggered.
}

try {
  const mod1 = await import("../plugins/onboard-product/OnboardProduct.jsx");
  OnboardProduct = mod1.OnboardProduct;
  const mod2 = await import("../plugins/llm-whisperer/helper.js");
  PRODUCT_NAMES = mod2.PRODUCT_NAMES ?? {};
} catch {
  // Do nothing.
}

try {
  const mod1 = await import(
    "../plugins/manual-review/page/ManualReviewPage.jsx"
  );
  ManualReviewPage = mod1.ManualReviewPage;
  const mod2 = await import(
    "../plugins/manual-review/review-layout/ReviewLayout.jsx"
  );
  ReviewLayout = mod2.ReviewLayout;
  const mod3 = await import(
    "../plugins/manual-review/page/simple/SimpleManualReviewPage.jsx"
  );
  SimpleManualReviewPage = mod3.SimpleManualReviewPage;
  const mod4 = await import("../plugins/manual-review/page/manage/Manage.jsx");
  Manage = mod4.Manage;
} catch {
  // Do nothing, Not-found Page will be triggered.
}

try {
  const mod1 = await import(
    "../plugins/unstract-subscription/pages/UnstractSubscriptionPage.jsx"
  );
  UnstractSubscriptionPage = mod1.UnstractSubscriptionPage;
  const mod2 = await import(
    "../plugins/unstract-subscription/pages/UnstractUsagePage.jsx"
  );
  UnstractUsagePage = mod2.UnstractUsagePage;
  const mod3 = await import(
    "../plugins/unstract-subscription/components/UnstractSubscriptionCheck.jsx"
  );
  UnstractSubscriptionCheck = mod3.UnstractSubscriptionCheck;
} catch {
  // Do nothing, Not-found Page will be triggered.
}

function useMainAppRoutes() {
  const routes = (
    <>
      <Route path=":orgName" element={<FullPageLayout />}>
        <Route path="onboard" element={<OnBoardPage />} />
      </Route>
      {ChatAppLayout && ChatAppPage && (
        <Route path=":orgName" element={<ChatAppLayout />}>
          <Route path="app/:id" element={<ChatAppPage />} />
        </Route>
      )}
      <Route path=":orgName" element={<PageLayout />}>
        {UnstractUsagePage && (
          <Route path="dashboard" element={<UnstractUsagePage />} />
        )}
        {UnstractSubscriptionPage && (
          <Route element={<RequireAdmin />}>
            <Route path="pricing" element={<UnstractSubscriptionPage />} />
          </Route>
        )}
        <Route
          path="admin/custom-plans"
          element={<UnstractAdministrationPage />}
        />
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
        {AgenticPromptStudio && (
          <Route
            path="agentic-prompt-studio/*"
            element={<AgenticPromptStudio />}
          />
        )}
        <Route path="logs" element={<LogsPage />} />
        <Route path="logs/:type/:id/" element={<LogsPage />} />
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
        <Route path="settings/connectors" element={<ConnectorsPage />} />
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
      {ReviewLayout && ManualReviewPage && (
        <Route path=":orgName" element={<ReviewLayout />}>
          <Route
            path="review"
            element={<ManualReviewPage type="review" />}
          ></Route>
          {SimpleManualReviewPage && (
            <>
              <Route
                path="simple_review/review"
                element={<SimpleManualReviewPage type="simple_review" />}
              ></Route>
              <Route
                path="simple_review/approve"
                element={<SimpleManualReviewPage type="simple_approve" />}
              ></Route>
            </>
          )}
          <Route
            path="review/download_and_sync"
            element={<ManualReviewPage type="download" />}
          />
          <Route
            path="review/approve"
            element={<ManualReviewPage type="approve" />}
          />
          {Manage && <Route path="review/manage" element={<Manage />} />}
        </Route>
      )}
    </>
  );

  if (OnboardProduct && Object.keys(PRODUCT_NAMES)?.length) {
    return (
      <Route
        path=""
        element={<OnboardProduct type={PRODUCT_NAMES?.unstract} />}
      >
        <Route path="" element={<UnstractSubscriptionCheck />}>
          {routes}
        </Route>
      </Route>
    );
  } else {
    return routes;
  }
}

export { useMainAppRoutes };
