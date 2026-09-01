import axios from "axios";
import { ThemeProvider, useTheme } from "next-themes";
import { DismissableLayer } from "radix-ui/internal";
import { useEffect } from "react";
import { HelmetProvider } from "react-helmet-async";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { ConfirmHost } from "@/components/widgets/confirm-modal/ConfirmHost";
import { showAppToast } from "@/hooks/useAppToast";
import { GenericLoader } from "./components/generic-loader/GenericLoader";
import CustomMarkdown from "./components/helpers/custom-markdown/CustomMarkdown.jsx";
import { NotificationClearAll } from "./components/notification/NotificationClearAll.jsx";
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
  const { sessionDetails, isLogoutLoading } = useSessionStore();
  const { alertDetails } = useAlertStore();
  const { pushLogMessages } = useSocketLogsStore();

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

    // P2-06: sonner is now the single notification surface. The antd
    // `notification` branch (and its btn/contextHolder scaffolding) is gone.
    // `description` carries the rendered markdown + ID lines that antd used to
    // display, so the alert body is unchanged.
    showAppToast(alertDetails, description);

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
    <>
      <HelmetProvider>
        <SyncShadcnTheme currentTheme={sessionDetails.currentTheme} />
        {isLogoutLoading && (
          <div className="fullscreen-loader">
            <GenericLoader />
          </div>
        )}
        <BrowserRouter>
          <PostHogPageviewTracker />
          <PageTitle title={"Unstract"} />
          {GoogleTagManagerHelper && <GoogleTagManagerHelper />}
          {/* Branch, so the toast stack is exempt from outside-dismissal:
              Radix would otherwise read a click on a toast as an interaction
              outside whatever layer is open and close it — dismissing an error
              toast would take the dialog that raised it, and the user's typed
              input, with it. The matching half of the fix is the
              `[data-sonner-toaster]` pointer-events rule in index.css, without
              which those clicks never land at all. */}
          <DismissableLayer.Branch>
            {/* top-right matches where antd's notification stack used to
                appear; sonner defaults to bottom-right (C4). The 56px offset
                reserves a band above the stack for the "Clear all" control —
                see `.notification-clear-all`, which pins itself into it. */}
            <Toaster position="top-right" offset={56} closeButton richColors />
            <NotificationClearAll />
          </DismissableLayer.Branch>
          {/* Mounted once here so a confirm dialog outlives whatever opened
              it — Delete sits inside a dropdown that unmounts on click. */}
          <ConfirmHost />
          <Router />
        </BrowserRouter>
      </HelmetProvider>
    </>
  );
}

/**
 * P0-15: mirror the existing session theme onto next-themes so ONE piece of
 * state drives both antd's algorithm and the `.dark` class that the Midnight
 * Bloom tokens key off.
 *
 * `sessionDetails.currentTheme` remains the single source of truth — this only
 * reflects it. How the theme is persisted, and where the user toggles it, are
 * deliberately unchanged (C4).
 */
function SyncShadcnTheme({ currentTheme }) {
  const { setTheme } = useTheme();

  useEffect(() => {
    setTheme(currentTheme === THEME.DARK ? THEME.DARK : THEME.LIGHT);
  }, [currentTheme, setTheme]);

  return null;
}

/**
 * next-themes owns the `.dark` class on <html>. `enableSystem` is off because
 * the app's theme is driven by the user's stored preference, not the OS.
 */
function AppWithProviders() {
  return (
    <ThemeProvider
      attribute="class"
      enableSystem={false}
      defaultTheme={THEME.LIGHT}
      disableTransitionOnChange
    >
      <App />
    </ThemeProvider>
  );
}

export { AppWithProviders as App };
