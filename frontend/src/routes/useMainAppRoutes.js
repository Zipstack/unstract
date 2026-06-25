import { lazy } from "react";
import { Route } from "react-router-dom";
import { RequireAdmin } from "../components/helpers/auth/RequireAdmin.js";
import { CustomToolsHelper } from "../components/helpers/custom-tools/CustomToolsHelper.js";
import { ProjectHelper } from "../components/helpers/project/ProjectHelper.js";
import { DefaultTriad } from "../components/settings/default-triad/DefaultTriad.jsx";
import { PlatformSettings } from "../components/settings/platform/PlatformSettings.jsx";
import { deploymentTypes } from "../helpers/GetStaticData.js";
import { isModuleMissing } from "../helpers/pluginLoader.js";
import { lazyPlugin } from "../helpers/pluginRegistry.js";

// Route pages are code-split so they are only fetched when navigated to,
// not eagerly on the unauthenticated /landing page. The <Suspense> boundary
// that renders these lives in Router.jsx (shared <Routes>).
const named = (loader, name) =>
  lazy(() => loader().then((m) => ({ default: m[name] })));

// The authenticated app shell is lazy too: it statically pulls in heavy nav
// widgets (which themselves eager-load plugins like lookup-studio), so keeping
// it eager would drag that whole graph onto /landing even though the shell
// never renders pre-login.
const FullPageLayout = named(
  () => import("../layouts/fullpage-payout/FullPageLayout.jsx"),
  "FullPageLayout",
);
const PageLayout = named(
  () => import("../layouts/page-layout/PageLayout.jsx"),
  "PageLayout",
);

const AgencyPage = named(() => import("../pages/AgencyPage.jsx"), "AgencyPage");
const ConnectorsPage = lazy(() => import("../pages/ConnectorsPage.jsx")); // default export
const CustomTools = named(
  () => import("../pages/CustomTools.jsx"),
  "CustomTools",
);
const DeploymentsPage = named(
  () => import("../pages/DeploymentsPage.jsx"),
  "DeploymentsPage",
);
const GroupsPage = named(() => import("../pages/GroupsPage.jsx"), "GroupsPage");
const InviteEditUserPage = named(
  () => import("../pages/InviteEditUserPage.jsx"),
  "InviteEditUserPage",
);
const LogsPage = named(() => import("../pages/LogsPage.jsx"), "LogsPage");
const MetricsDashboardPage = named(
  () => import("../pages/MetricsDashboardPage.jsx"),
  "MetricsDashboardPage",
);
const OnBoardPage = named(
  () => import("../pages/OnBoardPage.jsx"),
  "OnBoardPage",
);
const OutputAnalyzerPage = named(
  () => import("../pages/OutputAnalyzerPage.jsx"),
  "OutputAnalyzerPage",
);
const PlatformApiKeysPage = named(
  () => import("../pages/PlatformApiKeysPage.jsx"),
  "PlatformApiKeysPage",
);
const ProfilePage = named(
  () => import("../pages/ProfilePage.jsx"),
  "ProfilePage",
);
const SettingsPage = named(
  () => import("../pages/SettingsPage.jsx"),
  "SettingsPage",
);
const ToolIdePage = named(
  () => import("../pages/ToolIdePage.jsx"),
  "ToolIdePage",
);
const ToolsSettingsPage = named(
  () => import("../pages/ToolsSettingsPage.jsx"),
  "ToolsSettingsPage",
);
const UnstractAdministrationPage = named(
  () => import("../pages/UnstractAdministrationPage.jsx"),
  "UnstractAdministrationPage",
);
const UsersPage = named(() => import("../pages/UsersPage.jsx"), "UsersPage");
const WorkflowsPage = named(
  () => import("../pages/WorkflowsPage.jsx"),
  "WorkflowsPage",
);

// Enterprise plugin route elements — code-split (see lazyPlugin). Each returns
// a React.lazy component whose chunk loads only on navigation, so none are
// fetched on the /landing page. In OSS the import resolves to a stub and the
// element falls back to NotFound (route harmlessly 404s). The
// `{Component && <Route/>}` guards below are retained but always truthy.
const RequirePlatformAdmin = lazyPlugin(
  () => import("../plugins/frictionless-onboard/RequirePlatformAdmin.jsx"),
  "RequirePlatformAdmin",
);
const PlatformAdminPage = lazyPlugin(
  () =>
    import(
      "../plugins/frictionless-onboard/platform-admin-page/PlatformAdminPage.jsx"
    ),
  "PlatformAdminPage",
);
const AgenticPromptStudio = lazyPlugin(
  () => import("../plugins/agentic-prompt-studio"),
  "AgenticPromptStudio",
);
const LookupStudio = lazyPlugin(
  () => import("../plugins/lookup-studio"),
  "LookupStudio",
);
const AppDeployments = lazyPlugin(
  () => import("../plugins/app-deployment/AppDeployments.jsx"),
  "AppDeployments",
);
const ChatAppPage = lazyPlugin(
  () => import("../plugins/app-deployment/chat-app/ChatAppPage.jsx"),
  "ChatAppPage",
);
const ChatAppLayout = lazyPlugin(
  () => import("../plugins/app-deployment/chat-app/ChatAppLayout.jsx"),
  "ChatAppLayout",
);
const ManualReviewSettings = lazyPlugin(
  () => import("../plugins/manual-review/settings/Settings.jsx"),
  "ManualReviewSettings",
);
const OnboardProduct = lazyPlugin(
  () => import("../plugins/onboard-product/OnboardProduct.jsx"),
  "OnboardProduct",
);
const ManualReviewPage = lazyPlugin(
  () => import("../plugins/manual-review/page/ManualReviewPage.jsx"),
  "ManualReviewPage",
);
const ReviewLayout = lazyPlugin(
  () => import("../plugins/manual-review/review-layout/ReviewLayout.jsx"),
  "ReviewLayout",
);
const SimpleManualReviewPage = lazyPlugin(
  () =>
    import("../plugins/manual-review/page/simple/SimpleManualReviewPage.jsx"),
  "SimpleManualReviewPage",
);
const Manage = lazyPlugin(
  () => import("../plugins/manual-review/page/manage/Manage.jsx"),
  "Manage",
);
const ReadOnlyReviewPage = lazyPlugin(
  () => import("../plugins/prompt-change-indicator/ReadOnlyReviewPage.jsx"),
  "ReadOnlyReviewPage",
);
const UnstractSubscriptionPage = lazyPlugin(
  () =>
    import(
      "../plugins/unstract-subscription/pages/UnstractSubscriptionPage.jsx"
    ),
  "UnstractSubscriptionPage",
);
const UnstractSubscriptionCheck = lazyPlugin(
  () =>
    import(
      "../plugins/unstract-subscription/components/UnstractSubscriptionCheck.jsx"
    ),
  "UnstractSubscriptionCheck",
);
const MarketplaceLandingPage = lazyPlugin(
  () => import("../plugins/marketplace"),
  "MarketplaceLandingPage",
);
const MarketplaceStripeConflictPage = lazyPlugin(
  () => import("../plugins/marketplace"),
  "MarketplaceStripeConflictPage",
);

// PRODUCT_NAMES is a data value read synchronously below to decide the route
// tree, so it cannot be lazy — load it with a guarded await (cloud only; OSS
// resolves to the stub and is caught).
let PRODUCT_NAMES = {};
try {
  const mod = await import("../plugins/llm-whisperer/helper.js");
  PRODUCT_NAMES = mod.PRODUCT_NAMES ?? {};
} catch (err) {
  if (!isModuleMissing(err)) {
    // eslint-disable-next-line no-console
    console.error("[llm-whisperer] helper import failed unexpectedly", err);
  }
}

// The readonly route lives inside the manual-review ReviewLayout. If the
// prompt-change-indicator plugin ships without manual-review, the route
// would silently never register — surface that misconfiguration loudly.
if (ReadOnlyReviewPage && !ReviewLayout) {
  // eslint-disable-next-line no-console
  console.warn(
    "[prompt-change-indicator] ReadOnlyReviewPage loaded but ReviewLayout " +
      "is missing; readonly route will not be registered.",
  );
}

function useMainAppRoutes() {
  const routes = (
    <>
      <Route path=":orgName" element={<FullPageLayout />}>
        <Route path="onboard" element={<OnBoardPage />} />
        {MarketplaceLandingPage && (
          <Route
            path="marketplace-landing"
            element={<MarketplaceLandingPage />}
          />
        )}
        {MarketplaceStripeConflictPage && (
          <Route
            path="marketplace-stripe-conflict"
            element={<MarketplaceStripeConflictPage />}
          />
        )}
      </Route>
      {ChatAppLayout && ChatAppPage && (
        <Route path=":orgName" element={<ChatAppLayout />}>
          <Route path="app/:id" element={<ChatAppPage />} />
        </Route>
      )}
      <Route path=":orgName" element={<PageLayout />}>
        <Route path="dashboard" element={<MetricsDashboardPage />} />
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
        {LookupStudio && <Route path="lookups/*" element={<LookupStudio />} />}
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
          <Route path="groups" element={<GroupsPage />} />
          <Route
            path="settings/platform-api-keys"
            element={<PlatformApiKeysPage />}
          />
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
          {ReadOnlyReviewPage && (
            <Route
              path="review/readonly/:documentId"
              element={<ReadOnlyReviewPage />}
            />
          )}
        </Route>
      )}
    </>
  );

  // Gate on the exact value passed as `type` (PRODUCT_NAMES.unstract) rather
  // than on the map being non-empty, so we never wrap every route in
  // OnboardProduct with an undefined product type.
  const unstractProduct = PRODUCT_NAMES?.unstract;
  if (OnboardProduct && unstractProduct) {
    return (
      <Route path="" element={<OnboardProduct type={unstractProduct} />}>
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
