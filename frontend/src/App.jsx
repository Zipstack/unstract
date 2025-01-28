import { Button, ConfigProvider, notification, theme } from "antd";
import { BrowserRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";

import { THEME } from "./helpers/GetStaticData.js";
import { Router } from "./routes/Router.jsx";
import { useAlertStore } from "./store/alert-store.js";
import { useSessionStore } from "./store/session-store.js";
import PostHogPageviewTracker from "./PostHogPageviewTracker.js";
import { PageTitle } from "./components/widgets/page-title/PageTitle.jsx";
import { useEffect } from "react";
import CustomMarkdown from "./components/helpers/custom-markdown/CustomMarkdown.jsx";
import { useSocketLogsStore } from "./store/socket-logs-store.js";

let GoogleTagManagerHelper;
try {
  GoogleTagManagerHelper =
    require("./plugins/google-tag-manager-helper/GoogleTagManagerHelper.js").GoogleTagManagerHelper;
} catch {
  // The component will remain null of it is not available
}

function App() {
  const [notificationAPI, contextHolder] = notification.useNotification();
  const { defaultAlgorithm, darkAlgorithm } = theme;
  const { sessionDetails } = useSessionStore();
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
    if (!alertDetails?.content) return;

    notificationAPI.open({
      message: alertDetails?.title,
      description: <CustomMarkdown text={alertDetails?.content} />,
      type: alertDetails?.type,
      duration: alertDetails?.duration,
      btn,
      key: alertDetails?.key,
    });

    pushLogMessages([
      {
        timestamp: Math.floor(Date.now() / 1000),
        level: alertDetails?.type ? alertDetails?.type.toUpperCase() : "",
        message: alertDetails.content,
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
