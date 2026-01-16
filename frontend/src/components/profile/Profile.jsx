import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Spin, Tooltip, Typography } from "antd";
import {
  ArrowLeftOutlined,
  CopyOutlined,
  UserOutlined,
  MailOutlined,
  CheckCircleOutlined,
} from "@ant-design/icons";
import "./Profile.css";

import { useSessionStore } from "../../store/session-store.js";
import { useAlertStore } from "../../store/alert-store.js";
import { OrganizationIcon } from "../../assets";
import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";

function Profile() {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
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
      } catch {
        setAlertDetails({
          type: "error",
          content: "Could not refresh profile data",
        });
      } finally {
        setIsLoading(false);
      }
    };

    fetchProfile();
  }, [sessionDetails.orgId, axiosPrivate, setAlertDetails]);

  const handleCopy = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text || "");
      setAlertDetails({
        type: "success",
        content: `${label} copied to clipboard`,
      });
    } catch {
      setAlertDetails({
        type: "error",
        content: `Failed to copy ${label}`,
      });
    }
  };

  if (isLoading) {
    return (
      <div className="profile-page">
        {/* Secondary header bar - outside white container */}
        <div className="profile-secondary-header">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(-1)}
          />
          <Typography.Text strong className="profile-header-title">
            Profile
          </Typography.Text>
        </div>
        <div className="profile-outer-container">
          <div className="profile-loading">
            <Spin size="large" />
          </div>
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
      {/* Secondary header bar - outside white container */}
      <div className="profile-secondary-header">
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate(-1)}
        />
        <Typography.Text strong className="profile-header-title">
          Profile
        </Typography.Text>
      </div>
      {/* White container with cards only */}
      <div className="profile-outer-container">
        <div className="profile-content">
          <div className="profile-cards-row">
            {/* User Information Card */}
            <div className="profile-card">
              <div className="card-header">
                <div className="card-icon-circle user-icon">
                  <UserOutlined />
                </div>
                <div className="card-header-text">
                  <Typography.Text strong className="card-title">
                    User Information
                  </Typography.Text>
                  <Typography.Text type="secondary" className="card-subtitle">
                    Your personal account details
                  </Typography.Text>
                </div>
              </div>
              <div className="card-content">
                <div className="field-group">
                  <Typography.Text type="secondary" className="field-label">
                    Full Name
                  </Typography.Text>
                  <div className="field-box">
                    <Typography.Text className="field-value">
                      {userName}
                    </Typography.Text>
                    <UserOutlined className="field-icon" />
                  </div>
                </div>
                <div className="field-group">
                  <Typography.Text type="secondary" className="field-label">
                    Email Address
                  </Typography.Text>
                  <div className="field-box">
                    <Typography.Text className="field-value">
                      {email}
                    </Typography.Text>
                    <MailOutlined className="field-icon" />
                  </div>
                </div>
              </div>
            </div>

            {/* Organization Card */}
            <div className="profile-card">
              <div className="card-header">
                <div className="card-icon-circle org-icon">
                  <OrganizationIcon />
                </div>
                <div className="card-header-text">
                  <Typography.Text strong className="card-title">
                    Organization
                  </Typography.Text>
                  <Typography.Text type="secondary" className="card-subtitle">
                    Workspace and role information
                  </Typography.Text>
                </div>
              </div>
              <div className="card-content">
                <div className="field-group">
                  <Typography.Text type="secondary" className="field-label">
                    Organization Name
                  </Typography.Text>
                  <div className="field-box">
                    <Typography.Text className="field-value">
                      {orgName}
                    </Typography.Text>
                  </div>
                </div>
                <div className="field-group">
                  <Typography.Text type="secondary" className="field-label">
                    Organization ID
                  </Typography.Text>
                  <div className="field-with-action">
                    <div className="field-box">
                      <Typography.Text className="field-value org-id">
                        {orgId}
                      </Typography.Text>
                    </div>
                    <Tooltip title="Copy Organization ID">
                      <Button
                        type="text"
                        icon={<CopyOutlined />}
                        className="copy-button"
                        onClick={() => handleCopy(orgId, "Organization ID")}
                      />
                    </Tooltip>
                  </div>
                </div>
                {role && (
                  <div className="field-group">
                    <Typography.Text type="secondary" className="field-label">
                      Your Role
                    </Typography.Text>
                    <Typography.Text strong className="role-badge">
                      <CheckCircleOutlined />
                      {role}
                    </Typography.Text>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export { Profile };
