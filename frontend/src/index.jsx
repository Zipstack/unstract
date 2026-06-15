import posthog from "posthog-js";
import { PostHogProvider } from "posthog-js/react";
import React from "react";
import ReactDOM from "react-dom/client";

import { GenericLoader } from "./components/generic-loader/GenericLoader";
import { LazyLoader } from "./components/widgets/lazy-loader/LazyLoader.jsx";
import config from "./config.js";
import { getDeployment } from "./helpers/PostHogDeployment.js";
import { SocketProvider } from "./helpers/SocketContext.js";
import "./index.css";

// Runtime config (containerized deployments) wins when it carries a
// non-empty value; the entrypoint emits "" for unset env vars, which
// deliberately falls through to the build-time env
const runtimeConfig =
  typeof window !== "undefined" ? window.RUNTIME_CONFIG || {} : {};
const enablePosthog =
  runtimeConfig.enablePosthog || import.meta.env.VITE_ENABLE_POSTHOG;
if (enablePosthog !== "false") {
  // Analytics failures (blocked storage, ad-blockers, CSP) must never
  // abort module evaluation and block app bootstrap
  try {
    // Define the PostHog API key and host URL
    const API_KEY = "phc_PTafesyRuRB5hceRILaNPeyu2IDuzPshyjIPYGvgoBd"; // gitleaks:allow
    const API_HOST = "https://eu.i.posthog.com/";

    // Initialize PostHog with the specified API key and host
    posthog.init(API_KEY, {
      api_host: API_HOST,
      capture_pageview: false,
      autocapture: false,
      // Pre-login events stay anonymous (billed cheaper, no person created)
      person_profiles: "identified_only",
      respect_dnt: true,
    });
    posthog.register({ deployment: getDeployment() });
  } catch (error) {
    console.error("PostHog initialization failed:", error);
  }
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
  <React.StrictMode>
    <PostHogProvider client={posthog}>
      <SocketProvider>
        <LazyLoader
          loader={<GenericLoader />}
          component={() => import("./App.jsx")}
          componentName="App"
        />
      </SocketProvider>
    </PostHogProvider>
  </React.StrictMode>,
);
