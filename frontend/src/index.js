// import React from "react";
import ReactDOM from "react-dom/client";
import posthog from "posthog-js";
import { PostHogProvider } from "posthog-js/react";

import { Logo64 } from "./assets";
import { LazyLoader } from "./components/widgets/lazy-loader/LazyLoader.jsx";
import { SocketProvider } from "./helpers/SocketContext.js";
import "./index.css";

const API_KEY = "phc_f1kLKkipCK3kBtA9bT0SfAChvFrlUxYSMD91GBNbwr1"; // gitleaks:allow
const API_HOST = "https://app.posthog.com";
posthog.init(API_KEY, {
  api_host: API_HOST,
  capture_pageview: false,
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  // <React.StrictMode>
  <PostHogProvider client={posthog}>
    <SocketProvider>
      <LazyLoader
        loader={
          <div className="center">
            <Logo64 />
          </div>
        }
        component={() => import("./App.jsx")}
        componentName="App"
      />
    </SocketProvider>
  </PostHogProvider>
  // </React.StrictMode>
);
