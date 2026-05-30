import { Button, ConfigProvider, notification, theme } from "antd";
import axios from "axios";
import { useEffect } from "react";
import { HelmetProvider } from "react-helmet-async";
import { BrowserRouter } from "react-router-dom";
import { GenericLoader } from "./components/generic-loader/GenericLoader";
import CustomMarkdown from "./components/helpers/custom-markdown/CustomMarkdown.jsx";
import { NotificationIdLine } from "./components/notification/NotificationIdLine.jsx";
import { PageTitle } from "./components/widgets/page-title/PageTitle.jsx";
import { THEME } from "./helpers/GetStaticData.js";
import { attachRequestIdInterceptor } from "./helpers/requestId.js";
import PostHogPageviewTracker from "./PostHogPageviewTracker.js";
import { Router } from "./routes/Router.jsx";
import { useAlertStore } from "./store/alert-store.js";
import { useSessionStore } from "./store/session-store.js";
import { useSocketLogsStore } from "./store/socket-logs-store.js";

const GLOBAL_INTERCEPTOR_FLAG = Symbol.for("unstract.requestIdInterceptor");
if (!axios[GLOBAL_INTERCEPTOR_FLAG]) {
  attachRequestIdInterceptor(axios);
  axios[GLOBAL_INTERCEPTOR_FLAG] = true;
}

let GoogleTagManagerHelper;
try {
  const mod = await import(
    "./plugins/google-tag-manager-helper/GoogleTagManagerHelper.js"
  );
  GoogleTagManagerHelper = mod.GoogleTagManagerHelper;
} catch {
  // The component will remain null of it is not available
}

function App() {
  const [notificationAPI, contextHolder] = notification.useNotification();
  const { defaultAlgorithm, darkAlgorithm } = theme;
  const { sessionDetails, isLogoutLoading } = useSessionStore();
  const { alertDetails } = useAlertStore();
  const { pushLogMessages } = useSocketLogsStore();

  const btn = (
    <>
      <Button
        type="link"
        size="small"
        onClick={() => notificationAPI.destroy(alertDetails?.key)}
      >
        Close
      </Button>
      <Button
        type="link"
        size="small"
        onClick={() => notificationAPI.destroy()}
      >
        Close All
      </Button>
    </>
  );

  useEffect(() => {
    if (!alertDetails?.content) {
      return;
    }

    const showRequestId =
      alertDetails?.type === "error" && alertDetails?.requestId;
    const showExecutionId = Boolean(alertDetails?.executionId);
    const description = (
      <>
        <CustomMarkdown text={alertDetails?.content} />
        {showExecutionId && (
          <NotificationIdLine
            label="Execution ID"
            value={alertDetails?.executionId}
            stacked
          />
        )}
        {showRequestId && (
          <NotificationIdLine
            label="Request ID"
            value={alertDetails?.requestId}
          />
        )}
      </>
    );

    notificationAPI.open({
      message: alertDetails?.title,
      description,
      type: alertDetails?.type,
      duration: alertDetails?.duration,
      btn,
      key: alertDetails?.key,
    });

    const logSuffix = [
      showExecutionId && `Execution ID: \`${alertDetails.executionId}\``,
      showRequestId && `Request ID: \`${alertDetails.requestId}\``,
    ]
      .filter(Boolean)
      .join("\n");
    const logMessage = logSuffix
      ? `${alertDetails.content}\n${logSuffix}`
      : alertDetails.content;

    pushLogMessages([
      {
        timestamp: Math.floor(Date.now() / 1000),
        level: alertDetails?.type ? alertDetails?.type.toUpperCase() : "",
        message: logMessage,
        type: "NOTIFICATION",
      },
    ]);
  }, [alertDetails]);

  return (
    <ConfigProvider
      direction={window.direction || "ltr"}
      theme={{
        algorithm:
          sessionDetails.currentTheme === THEME.DARK
            ? darkAlgorithm
            : defaultAlgorithm,
        components: {
          Button: {
            colorPrimary: "#092C4C",
            colorPrimaryHover: "#0e4274",
            colorPrimaryActive: "#092C4C",
          },
        },
      }}
    >
      <HelmetProvider>
        {isLogoutLoading && (
          <div className="fullscreen-loader">
            <GenericLoader />
          </div>
        )}
        <BrowserRouter>
          <PostHogPageviewTracker />
          <PageTitle title={"Unstract"} />
          {GoogleTagManagerHelper && <GoogleTagManagerHelper />}
          {contextHolder}
          <Router />
        </BrowserRouter>
      </HelmetProvider>
    </ConfigProvider>
  );
}

export { App };
