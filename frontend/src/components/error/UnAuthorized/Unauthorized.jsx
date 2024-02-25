import { Typography } from "antd";

import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import "./Unauthorized.css";

function Unauthorized() {
  return (
    <IslandLayout>
      <div className="unauth-container">
        <Typography className="unauth-text">
          Sorry, you dont have access to this page. Please contact the
          administrator for assistance.
        </Typography>
      </div>
    </IslandLayout>
  );
}

export { Unauthorized };
