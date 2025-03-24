import { Typography } from "antd";
import { useNavigate } from "react-router-dom";
import "./Settings.css";

import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import { useSessionStore } from "../../../store/session-store";
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";

function Settings() {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const { setPostHogCustomEvent } = usePostHogEvents();
  const handleDefaultTriadClick = () => {
    navigate("triad");

    try {
      setPostHogCustomEvent("intent_select_default_triad", {
        info: "Clicked on 'Default Triad' button",
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  return (
    <div className="settings-bg-col">
      <IslandLayout>
        <div className="settings-layout">
          <div className="settings-head">
            <Typography.Text className="settings-head-typo">
              General Settings
            </Typography.Text>
          </div>
          <div className="settings-plt">
            <Typography.Link
              className="settings-plt-typo"
              strong
              onClick={() => navigate("platform")}
            >
              Platform Settings
            </Typography.Link>
          </div>
          <div className="settings-plt">
            <Typography.Link
              className="settings-plt-typo"
              strong
              onClick={() => navigate(`/${sessionDetails?.orgName}/users`)}
            >
              User Management
            </Typography.Link>
          </div>
          <div className="settings-plt">
            <Typography.Link
              className="settings-plt-typo"
              strong
              onClick={handleDefaultTriadClick}
            >
              Default Triad
            </Typography.Link>
          </div>

          {sessionDetails?.isPlatformAdmin && (
            <div className="settings-plt">
              <Typography.Link
                className="settings-plt-typo"
                strong
                onClick={() => navigate("admin")}
              >
                Admin settings
              </Typography.Link>
            </div>
          )}
          <div className="settings-plt">
            <Typography.Link
              className="settings-plt-typo"
              strong
              onClick={() => navigate("review")}
            >
              Human In The Loop Settings
            </Typography.Link>
          </div>
        </div>
      </IslandLayout>
    </div>
  );
}

export { Settings };
