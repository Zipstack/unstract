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
import { LogsPage } from "../pages/LogsPage.jsx";
import { deploymentTypes } from "../helpers/GetStaticData.js";

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
let UnstractUsagePage;
let UnstractSubscriptionPage;
let UnstractSubscriptionCheck;

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

try {
  OnboardProduct =
    require("../plugins/onboard-product/OnboardProduct.jsx").OnboardProduct;
  PRODUCT_NAMES = require("../plugins/llm-whisperer/helper.js").PRODUCT_NAMES;
} catch (err) {
  // Do nothing.
}

try {
  ManualReviewPage =
    require("../plugins/manual-review/page/ManualReviewPage.jsx").ManualReviewPage;
  ReviewLayout =
    require("../plugins/manual-review/review-layout/ReviewLayout.jsx").ReviewLayout;
  SimpleManualReviewPage =
    require("../plugins/manual-review/page/simple/SimpleManualReviewPage.jsx").SimpleManualReviewPage;
} catch (err) {
  // Do nothing, Not-found Page will be triggered.
}

try {
  UnstractSubscriptionPage =
    require("../plugins/unstract-subscription/pages/UnstractSubscriptionPage.jsx").UnstractSubscriptionPage;
  UnstractUsagePage =
    require("../plugins/unstract-subscription/pages/UnstractUsagePage.jsx").UnstractUsagePage;
  UnstractSubscriptionCheck =
    require("../plugins/unstract-subscription/components/UnstractSubscriptionCheck.jsx").UnstractSubscriptionCheck;
} catch (err) {
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
          <Route
            path="simple_review/review"
            element={<SimpleManualReviewPage type="simple_review" />}
          ></Route>
          <Route
            path="simple_review/approve"
            element={<SimpleManualReviewPage type="simple_approve" />}
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
