import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Spin, Tooltip, message } from "antd";
import {
  ArrowLeftOutlined,
  CopyOutlined,
  UserOutlined,
  BankOutlined,
  MailOutlined,
  CheckCircleOutlined,
} from "@ant-design/icons";
import "./Profile.css";

import { useSessionStore } from "../../store/session-store.js";
import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";

function Profile() {
  const navigate = useNavigate();
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
  }, [sessionDetails.orgId]);

  const handleCopy = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text || "");
      message.success(`${label} copied to clipboard`);
    } catch {
      message.error(`Failed to copy ${label}`);
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
          <span className="profile-header-title">Profile</span>
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
        <span className="profile-header-title">Profile</span>
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
                  <div className="card-title">User Information</div>
                  <div className="card-subtitle">
                    Your personal account details
                  </div>
                </div>
              </div>
              <div className="card-content">
                <div className="field-group">
                  <label className="field-label">Full Name</label>
                  <div className="field-box">
                    <span className="field-value">{userName}</span>
                    <UserOutlined className="field-icon" />
                  </div>
                </div>
                <div className="field-group">
                  <label className="field-label">Email Address</label>
                  <div className="field-box">
                    <span className="field-value">{email}</span>
                    <MailOutlined className="field-icon" />
                  </div>
                </div>
              </div>
            </div>

            {/* Organisation Card */}
            <div className="profile-card">
              <div className="card-header">
                <div className="card-icon-circle org-icon">
                  <BankOutlined />
                </div>
                <div className="card-header-text">
                  <div className="card-title">Organisation</div>
                  <div className="card-subtitle">
                    Workspace and role information
                  </div>
                </div>
              </div>
              <div className="card-content">
                <div className="field-group">
                  <label className="field-label">Organization Name</label>
                  <div className="field-box">
                    <span className="field-value">{orgName}</span>
                  </div>
                </div>
                <div className="field-group">
                  <label className="field-label">Organisation ID</label>
                  <div className="field-with-action">
                    <div className="field-box">
                      <span className="field-value org-id">{orgId}</span>
                    </div>
                    <Tooltip title="Copy Organisation ID">
                      <Button
                        type="text"
                        icon={<CopyOutlined />}
                        className="copy-button"
                        onClick={() => handleCopy(orgId, "Organisation ID")}
                      />
                    </Tooltip>
                  </div>
                </div>
                {role && (
                  <div className="field-group">
                    <label className="field-label">Your Role</label>
                    <span className="role-badge">
                      <CheckCircleOutlined />
                      {role}
                    </span>
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
