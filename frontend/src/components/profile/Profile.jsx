import { Button, Input, Space, Typography } from "antd";
import "./Profile.css";

import { useSessionStore } from "../../store/session-store.js";

function Profile() {
  const { sessionDetails } = useSessionStore();

  return (
    <div className="grey-body">
      <div className="paper-layout">
        <div className="header-text">
          <Typography.Text className="typo-text" strong>
            User Profile
          </Typography.Text>
        </div>

        <Space direction="vertical" size="middle">
          <div>
            <Typography.Text strong>User Name:</Typography.Text>
            <Input defaultValue={sessionDetails.display_name} readOnly />
          </div>
          <div>
            <Typography.Text strong>Email:</Typography.Text>
            <Input defaultValue={sessionDetails.email} readOnly />
          </div>
          {sessionDetails.roles && (
            <div>
              <Typography.Text strong>Roles:</Typography.Text>
              <Input defaultValue={sessionDetails.roles} readOnly />
            </div>
          )}

          <Button disabled>Reset Password</Button>
        </Space>
      </div>
    </div>
  );
}

export { Profile };
