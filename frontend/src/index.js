// import React from "react";
import ReactDOM from "react-dom/client";
import posthog from "posthog-js";
import { PostHogProvider } from "posthog-js/react";

import { GenericLoader } from "./components/generic-loader/GenericLoader";
import { LazyLoader } from "./components/widgets/lazy-loader/LazyLoader.jsx";
import { SocketProvider } from "./helpers/SocketContext.js";
import "./index.css";
import config from "./config.js";

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

// Utility to set favicon
function setFavicon(url) {
  let link = document.querySelector("link[rel~='icon']");
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    document.head.appendChild(link);
  }
  link.href = url;
}

// Call this after config is loaded
setFavicon(config.favicon);

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  // <React.StrictMode>
  <PostHogProvider client={posthog}>
    <SocketProvider>
      <LazyLoader
        loader={<GenericLoader />}
        component={() => import("./App.jsx")}
        componentName="App"
      />
    </SocketProvider>
  </PostHogProvider>
  // </React.StrictMode>
);
