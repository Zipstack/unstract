import ReactDOM from "react-dom/client";
import posthog from "posthog-js";
import { PostHogProvider } from "posthog-js/react";

import { GenericLoader } from "./components/generic-loader/GenericLoader";
import { LazyLoader } from "./components/widgets/lazy-loader/LazyLoader.jsx";
import { SocketProvider } from "./helpers/SocketContext.js";
import "./index.css";

const enablePosthog = process.env.REACT_APP_ENABLE_POSTHOG;
if (enablePosthog !== "false") {
  // Define the PostHog API key and host URL
  const API_KEY = "phc_PTafesyRuRB5hceRILaNPeyu2IDuzPshyjIPYGvgoBd"; // gitleaks:allow
  const API_HOST = "https://eu.i.posthog.com/";

  // Initialize PostHog with the specified API key and host
  posthog.init(API_KEY, {
    api_host: API_HOST,
    capture_pageview: false,
    autocapture: false,
  });
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <PostHogProvider client={posthog}>
    <SocketProvider>
      <LazyLoader
        loader={<GenericLoader />}
        component={() => import("./App.jsx")}
        componentName="App"
      />
    </SocketProvider>
  </PostHogProvider>
);
