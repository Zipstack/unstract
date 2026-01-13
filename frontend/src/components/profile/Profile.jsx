import { useState, useEffect } from "react";
import {
  Button,
  Card,
  Descriptions,
  Space,
  Spin,
  Tooltip,
  Typography,
  message,
} from "antd";
import { CopyOutlined, UserOutlined, BankOutlined } from "@ant-design/icons";
import "./Profile.css";

import { useSessionStore } from "../../store/session-store.js";
import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";

function Profile() {
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const [profileData, setProfileData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchProfile = async () => {
      if (!sessionDetails.orgId) {
        setIsLoading(false);
        return;
      }

      try {
        const response = await axiosPrivate({
          url: `/api/v1/unstract/${sessionDetails.orgId}/users/profile/`,
          method: "GET",
        });
        setProfileData(response.data?.user);
      } catch (error) {
        console.error("Failed to fetch profile:", error);
        message.warning("Could not refresh profile data");
      } finally {
        setIsLoading(false);
      }
    };

    fetchProfile();
  }, [sessionDetails.orgId, axiosPrivate]);

  const handleCopy = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text || "");
      message.success(`${label} copied to clipboard`);
    } catch {
      message.error(`Failed to copy ${label}`);
    }
  };

  const renderCopyButton = (value, label) => (
    <Tooltip title={`Copy ${label}`}>
      <CopyOutlined
        className="copy-icon"
        onClick={() => handleCopy(value, label)}
      />
    </Tooltip>
  );

  if (isLoading) {
    return (
      <div className="profile-page">
        <div className="profile-loading">
          <Spin size="large" />
        </div>
      </div>
    );
  }

  const userName = profileData?.display_name || sessionDetails.display_name;
  const email = profileData?.email || sessionDetails.email;
  const orgName = profileData?.organization_name || sessionDetails.orgName;
  const orgId = profileData?.organization_id || sessionDetails.orgId;
  const role = profileData?.role || sessionDetails.role;

  return (
    <div className="profile-page">
      <div className="profile-container">
        <Typography.Title level={4} className="profile-title">
          Profile
        </Typography.Title>

        <Space direction="vertical" size="middle" className="profile-cards">
          <Card
            title={
              <span className="card-title">
                <UserOutlined className="card-icon" />
                User Information
              </span>
            }
            className="profile-card"
          >
            <Descriptions column={1} colon={false}>
              <Descriptions.Item label="User Name">
                {userName}
              </Descriptions.Item>
              <Descriptions.Item label="Email">{email}</Descriptions.Item>
            </Descriptions>
          </Card>

          <Card
            title={
              <span className="card-title">
                <BankOutlined className="card-icon" />
                Organization
              </span>
            }
            className="profile-card"
          >
            <Descriptions column={1} colon={false}>
              <Descriptions.Item
                label="Name"
                contentStyle={{ display: "flex", alignItems: "center", gap: 8 }}
              >
                <span className="description-value">{orgName}</span>
                {renderCopyButton(orgName, "Organization name")}
              </Descriptions.Item>
              <Descriptions.Item
                label="ID"
                contentStyle={{ display: "flex", alignItems: "center", gap: 8 }}
              >
                <span className="description-value org-id">{orgId}</span>
                {renderCopyButton(orgId, "Organization ID")}
              </Descriptions.Item>
              {role && (
                <Descriptions.Item label="Your Role">
                  <span className="role-badge">{role}</span>
                </Descriptions.Item>
              )}
            </Descriptions>
          </Card>

          <div className="profile-actions">
            <Button disabled>Reset Password</Button>
          </div>
        </Space>
      </div>
    </div>
  );
}

export { Profile };
