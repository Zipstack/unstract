import { Typography } from "antd";
import { useNavigate } from "react-router-dom";
import "./Settings.css";

import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import { useSessionStore } from "../../../store/session-store";

function Settings() {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();

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
              User Settings
            </Typography.Link>
          </div>
          <div className="settings-plt">
            <Typography.Link
              className="settings-plt-typo"
              strong
              onClick={() => navigate("triad")}
            >
              Default Triad
            </Typography.Link>
          </div>
          <div className="settings-plt">
            <Typography.Link
              className="settings-plt-typo"
              strong
              onClick={() => navigate("/admin")}
            >
              Admin settings
            </Typography.Link>
          </div>
        </div>
      </IslandLayout>
    </div>
  );
}

export { Settings };
