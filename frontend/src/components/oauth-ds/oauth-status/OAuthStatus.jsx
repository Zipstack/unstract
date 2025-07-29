import { Typography } from "antd";
import { useLocation } from "react-router-dom";

import "./OAuthStatus.css";

const SUCCESS = "success";
const DANGER = "danger";

function OAuthStatus() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const status = params.get("status");

  // Set connector-specific status only - no global oauth-status to prevent contamination
  const currentConnector = localStorage.getItem("oauth-current-connector");
  if (currentConnector) {
    const statusKey = `oauth-status-${currentConnector}`;
    localStorage.setItem(statusKey, status);
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
