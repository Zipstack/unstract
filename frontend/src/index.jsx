import posthog from "posthog-js";
import { PostHogProvider } from "posthog-js/react";
import React from "react";
import ReactDOM from "react-dom/client";

import { GenericLoader } from "./components/generic-loader/GenericLoader";
import { LazyLoader } from "./components/widgets/lazy-loader/LazyLoader.jsx";
import { SocketProvider } from "./helpers/SocketContext.js";
import "./index.css";
import config from "./config.js";

const enablePosthog = import.meta.env.VITE_ENABLE_POSTHOG;
if (enablePosthog !== "false") {
  // Define the PostHog API key and host URL
  const API_KEY = "phc_PTafesyRuRB5hceRILaNPeyu2IDuzPshyjIPYGvgoBd"; // gitleaks:allow
  const API_HOST = "https://eu.i.posthog.com/";

  // All deployments report to a single PostHog project; tag events with
  // their origin so they can be segmented
  const DEPLOYMENT_BY_HOST = {
    "us-central.unstract.com": "us-prod",
    "eu-west.unstract.com": "eu-prod",
  };
  const getDeployment = () => {
    const hostname = window.location.hostname;
    if (DEPLOYMENT_BY_HOST[hostname]) {
      return DEPLOYMENT_BY_HOST[hostname];
    }
    if (hostname.endsWith("globe.unstract.com")) {
      return "saas-staging";
    }
    if (hostname === "localhost" || hostname.endsWith(".localhost")) {
      return "dev";
    }
    return "self-hosted";
  };

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
