import { ConfigProvider, notification, theme } from "antd";
import { BrowserRouter } from "react-router-dom";

import { THEME } from "./helpers/GetStaticData.js";
import { Router } from "./routes/Router.jsx";
import { useAlertStore } from "./store/alert-store.js";
import { useSessionStore } from "./store/session-store.js";
import PostHogPageviewTracker from "./PostHogPageviewTracker.js";

function App() {
  const [notificationAPI, contextHolder] = notification.useNotification();
  const { defaultAlgorithm, darkAlgorithm } = theme;
  const { sessionDetails } = useSessionStore();
  const { alertDetails } = useAlertStore();

  alertDetails.content &&
    notificationAPI.open({
      message: alertDetails.title,
      description: alertDetails.content,
      type: alertDetails.type,
      duration: 0,
    });

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
      <BrowserRouter>
        <PostHogPageviewTracker />
        {contextHolder}
        <Router />
      </BrowserRouter>
    </ConfigProvider>
  );
}

export { App };
