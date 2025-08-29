import { Typography } from "antd";
import { useLocation } from "react-router-dom";

import "./OAuthStatus.css";

const SUCCESS = "success";
const DANGER = "danger";

function OAuthStatus() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const status = params.get("status");

  // Set status for the connector that initiated OAuth (stored in sessionStorage for callback)
  const currentConnector = sessionStorage.getItem("oauth-current-connector");
  if (currentConnector) {
    // currentConnector contains the selectedSourceId
    const statusKey = `oauth-status-${currentConnector}`;
    localStorage.setItem(statusKey, status);
    // Clear the session storage after use
    sessionStorage.removeItem("oauth-current-connector");
  }

  if (status === SUCCESS) {
    setTimeout(() => {
      window.close();
    }, 1000);
  }

  return (
    <div className="display-flex-center oauth-status-layout">
      <Typography.Text
        type={status === SUCCESS ? SUCCESS : DANGER}
        className="oauth-status-text"
      >
        {"Authentication " + (status === SUCCESS ? "Successful" : "Failed")}
      </Typography.Text>
    </div>
  );
}

export { OAuthStatus };
