import {
  Alert,
  Button,
  Col,
  Dropdown,
  Image,
  Row,
  Space,
  Typography,
} from "antd";
import {
  UserOutlined,
  UserSwitchOutlined,
  LogoutOutlined,
  DownloadOutlined,
  FileProtectOutlined,
  LikeOutlined,
} from "@ant-design/icons";
import { useEffect, useState, useMemo, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import axios from "axios";
import PropTypes from "prop-types";

import { UnstractLogo } from "../../../assets/index.js";
import {
  getBaseUrl,
  homePagePath,
  onboardCompleted,
} from "../../../helpers/GetStaticData.js";
import useLogout from "../../../hooks/useLogout.js";
import "../../../layouts/page-layout/PageLayout.css";
import { useSessionStore } from "../../../store/session-store.js";
import "./TopNavBar.css";
import { useAlertStore } from "../../../store/alert-store.js";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal.jsx";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";

let TrialDaysInfo;
try {
  TrialDaysInfo =
    require("../../../plugins/subscription/trial-helper/TrialDaysInfo.jsx").default;
} catch (err) {
  // Plugin not found
}

let selectedProductStore;
let selectedProduct;

try {
  selectedProductStore = require("../../../plugins/llm-whisperer/store/select-product-store.js");
} catch {
  // Ignore if hook not available
}

let PlatformDropdown;
try {
  PlatformDropdown =
    require("../../../plugins/platform-dropdown/PlatformDropDown.jsx").PlatformDropdown;
} catch (err) {
  // Plugin not found
}

let WhispererLogo;
try {
  WhispererLogo =
    require("../../../plugins/assets/llmWhisperer/index.js").WhispererLogo;
} catch {
  // Ignore if hook not available
}

function TopNavBar({ isSimpleLayout, topNavBarOptions }) {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const { orgName, allOrganization, orgId } = sessionDetails;
  const baseUrl = getBaseUrl();
  const onBoardUrl = `${baseUrl}/${orgName}/onboard`;
  const logout = useLogout();
  const [showOnboardBanner, setShowOnboardBanner] = useState(false);
  const [approverStatus, setApproverStatus] = useState(false);
  const [reviewerStatus, setReviewerStatus] = useState(false);
  const [reviewPageHeader, setReviewPageHeader] = useState("");
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const location = useLocation();

  if (selectedProductStore) {
    selectedProduct = selectedProductStore.useSelectedProductStore(
      (state) => state?.selectedProduct
    );
  }

  const isUnstract = !(selectedProduct && selectedProduct !== "unstract");

  // Check user role and whether the onboarding is incomplete
  useEffect(() => {
    const { role } = sessionDetails;
    const isReviewer = role === "unstract_reviewer";
    const isSupervisor = role === "unstract_supervisor";
    const isAdmin = role === "unstract_admin";

    setShowOnboardBanner(
      !onboardCompleted(sessionDetails?.adapters) &&
        !isReviewer &&
        !isSupervisor
    );
    setApproverStatus(isAdmin || isSupervisor);
    setReviewerStatus(isReviewer);
  }, [sessionDetails]);

  // Determine review page header
  useEffect(() => {
    const pathSegments = location.pathname.split("review");
    if (pathSegments.length > 1) {
      if (pathSegments[1].includes("/approve")) {
        setReviewPageHeader("Approve");
      } else if (pathSegments[1].includes("/download_and_sync")) {
        setReviewPageHeader("Download and syncmanager");
      } else {
        setReviewPageHeader("Review");
      }
    } else {
      setReviewPageHeader(null);
    }
    if (location.pathname.includes("/simple_review")) {
      setReviewPageHeader("Simple Review");
    }
  }, [location]);

  // Switch organization
  const handleContinue = useCallback(async (selectedOrg) => {
    const requestOptions = {
      method: "POST",
      url: `/api/v1/organization/${selectedOrg}/set`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    try {
      await axios(requestOptions);
      navigate("/");
      window.location.reload();
    } catch (err) {
      setAlertDetails(handleException(err));
    }
  }, []);

  // Prepare org list for switching
  const cascadeOptions = useMemo(() => {
    return allOrganization?.map((org) => {
      return {
        key: org?.id,
        label:
          org?.id === sessionDetails?.orgId ? (
            <div
              onClick={() =>
                setAlertDetails({
                  type: "error",
                  content: `You are already in ${org?.display_name}`,
                })
              }
            >
              {org?.display_name}
            </div>
          ) : (
            <ConfirmModal
              handleConfirm={() => handleContinue(org?.id)}
              content={`Want to switch to ${org?.display_name}?`}
            >
              <div>{org?.display_name}</div>
            </ConfirmModal>
          ),
      };
    });
  }, [allOrganization, handleContinue]);

  // Build dropdown menu items
  const items = useMemo(() => {
    const menuItems = [];

    // Profile
    if (isUnstract && !isSimpleLayout) {
      menuItems.push({
        key: "1",
        label: (
          <Button
            onClick={() => navigate(`/${orgName}/profile`)}
            className="logout-button"
          >
            <UserOutlined /> Profile
          </Button>
        ),
      });
    }

    // Switch Organization
    if (allOrganization?.length > 1) {
      menuItems.push({
        key: "3",
        label: (
          <Dropdown
            placeholder="Switch Organization"
            menu={{
              items: cascadeOptions,
              selectable: true,
              selectedKeys: [orgId],
              className: "switch-org-menu",
            }}
            placement="left"
          >
            <div>
              <UserSwitchOutlined /> Switch Org
            </div>
          </Dropdown>
        ),
      });
    }

    // Review
    if (isUnstract && !isSimpleLayout && (reviewerStatus || approverStatus)) {
      menuItems.push({
        key: "4",
        label: (
          <Button
            onClick={() => navigate(`/${orgName}/review`)}
            className="logout-button"
          >
            <FileProtectOutlined /> Review
          </Button>
        ),
      });
    }

    // Approve
    if (isUnstract && !isSimpleLayout && approverStatus) {
      menuItems.push({
        key: "5",
        label: (
          <Button
            onClick={() => navigate(`/${orgName}/review/approve`)}
            className="logout-button"
          >
            <LikeOutlined /> Approve
          </Button>
        ),
      });

      menuItems.push({
        key: "6",
        label: (
          <Button
            onClick={() => navigate(`/${orgName}/review/download_and_sync`)}
            className="logout-button"
          >
            <DownloadOutlined /> Download and Sync Manager
          </Button>
        ),
      });
    }

    // Logout
    menuItems.push({
      key: "2",
      label: (
        <Button onClick={logout} className="logout-button">
          <LogoutOutlined /> Logout
        </Button>
      ),
    });

    return menuItems.filter(Boolean); // remove any undefined items
  }, [
    isUnstract,
    isSimpleLayout,
    reviewerStatus,
    approverStatus,
    allOrganization,
    cascadeOptions,
    orgName,
    orgId,
  ]);

  // Function to get the initials from the user name
  const getInitials = useCallback((name) => {
    const names = name?.split(" ");
    return names
      ?.map((n) => n.charAt(0))
      ?.join("")
      ?.toUpperCase();
  }, []);

  return (
    <Row align="middle" className="topNav">
      <Col span={6} className="platform-switch-container">
        {isUnstract ? (
          <UnstractLogo
            className="topbar-logo cursor-pointer"
            onClick={() =>
              navigate(`/${sessionDetails?.orgName}/${homePagePath}`)
            }
          />
        ) : (
          WhispererLogo && <WhispererLogo className="topbar-logo" />
        )}
        {reviewPageHeader && (
          <span className="page-identifier">
            <span className="custom-tools-header-v-divider" />
            <span className="page-heading">{reviewPageHeader}</span>
          </span>
        )}
        {PlatformDropdown && <PlatformDropdown />}
      </Col>

      {isSimpleLayout ? (
        <Col span={14} />
      ) : (
        <Col span={14} className="top-nav-alert-col">
          {isUnstract && showOnboardBanner && (
            <Alert
              type="error"
              message={
                <>
                  <span className="top-nav-alert-msg">
                    Your setup process is incomplete. Now, that&apos;s a bummer!
                  </span>
                  <a href={onBoardUrl} className="top-nav-alert-link">
                    Complete it to start using Unstract
                  </a>
                </>
              }
              showIcon
            />
          )}
        </Col>
      )}

      <Col span={4}>
        <Row justify="end" align="middle">
          <Space>
            {topNavBarOptions}
            {isUnstract && TrialDaysInfo && <TrialDaysInfo />}
            <Dropdown menu={{ items }} placement="bottomLeft" arrow>
              <div className="top-navbar-dp">
                {sessionDetails?.picture ? (
                  <Image
                    className="navbar-img"
                    height="100%"
                    width="100%"
                    preview={false}
                    src={sessionDetails?.picture}
                  />
                ) : (
                  <Typography.Text className="initials">
                    {getInitials(sessionDetails?.name)}
                  </Typography.Text>
                )}
              </div>
            </Dropdown>
          </Space>
        </Row>
      </Col>
    </Row>
  );
}

TopNavBar.propTypes = {
  isSimpleLayout: PropTypes.bool,
  topNavBarOptions: PropTypes.node,
};

export { TopNavBar };
