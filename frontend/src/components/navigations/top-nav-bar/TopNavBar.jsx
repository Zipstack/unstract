import {
  Alert,
  Button,
  Col,
  Dropdown,
  Row,
  Space,
  Typography,
  Image,
} from "antd";
import {
  UserOutlined,
  UserSwitchOutlined,
  LogoutOutlined,
  DownloadOutlined,
  FileProtectOutlined,
  LikeOutlined,
  LoginOutlined,
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
  UNSTRACT_ADMIN,
} from "../../../helpers/GetStaticData.js";
import useLogout from "../../../hooks/useLogout.js";
import "../../../layouts/page-layout/PageLayout.css";
import { useSessionStore } from "../../../store/session-store.js";
import "./TopNavBar.css";
import { useAlertStore } from "../../../store/alert-store.js";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal.jsx";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import config from "../../../config";

let TrialDaysInfo;
try {
  TrialDaysInfo =
    require("../../../plugins/unstract-subscription/components/TrialDaysInfo.jsx").default;
} catch (err) {
  // Plugin not found
}

let selectedProductStore;
let selectedProduct;

try {
  selectedProductStore = require("../../../plugins/store/select-product-store.js");
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

const CustomLogo = ({ onClick, className }) => {
  // Use Ant Design Image and config.logoUrl
  if (config.logoUrl) {
    return (
      <Image
        src={config.logoUrl}
        preview={false}
        className={className}
        onClick={onClick}
        alt="logo"
        width={120}
        style={{
          cursor: onClick ? "pointer" : undefined,
          background: "transparent",
        }}
        onError={() => {
          // If image fails to load, component will re-render and use UnstractLogo
          // since we'll set config.logoUrl to null
          if (config.logoUrl) {
            // Only modify if it's not already null to avoid infinite re-renders
            config.logoUrl = null;
          }
        }}
      />
    );
  }
  return <UnstractLogo className={className} onClick={onClick} />;
};
// let APIHubLogo;
// try {
//   APIHubLogo = require("../../../plugins/assets/verticals/index.js").APIHubLogo;
// } catch {
//   // Ignore if hook not available
// }

let unstractSubscriptionPlan;
let unstractSubscriptionPlanStore;
let UNSTRACT_SUBSCRIPTION_PLANS;
let UnstractPricingMenuLink;
try {
  unstractSubscriptionPlanStore = require("../../../plugins/store/unstract-subscription-plan-store");
  UNSTRACT_SUBSCRIPTION_PLANS =
    require("../../../plugins/unstract-subscription/helper/constants").UNSTRACT_SUBSCRIPTION_PLANS;
  UnstractPricingMenuLink =
    require("../../../plugins/unstract-subscription/components/UnstractPricingMenuLink.jsx").UnstractPricingMenuLink;
} catch (err) {
  // Plugin unavailable.
}

function TopNavBar({ isSimpleLayout, topNavBarOptions }) {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const { orgName, allOrganization, orgId, isLoggedIn } = sessionDetails;
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

  try {
    if (unstractSubscriptionPlanStore?.useUnstractSubscriptionPlanStore) {
      unstractSubscriptionPlan =
        unstractSubscriptionPlanStore?.useUnstractSubscriptionPlanStore(
          (state) => state?.unstractSubscriptionPlan
        );
    }
  } catch (error) {
    // Do nothing
  }

  const shouldDisableRouting = useMemo(() => {
    if (!unstractSubscriptionPlan || !UNSTRACT_SUBSCRIPTION_PLANS) {
      return false;
    }

    return unstractSubscriptionPlan?.remainingDays <= 0;
  }, [unstractSubscriptionPlan]);

  const isUnstract = !(selectedProduct && selectedProduct !== "unstract");
  // const isAPIHub = selectedProduct && selectedProduct === "verticals";

  // Check user role and whether the onboarding is incomplete
  useEffect(() => {
    const { role } = sessionDetails;
    const isReviewer = role === "unstract_reviewer";
    const isSupervisor = role === "unstract_supervisor";
    const isAdmin = role === UNSTRACT_ADMIN;

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
            disabled={shouldDisableRouting}
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
            disabled={shouldDisableRouting}
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
            disabled={shouldDisableRouting}
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
            disabled={shouldDisableRouting}
          >
            <DownloadOutlined /> Download and Sync Manager
          </Button>
        ),
      });
    }

    if (isUnstract && UnstractPricingMenuLink && sessionDetails?.isAdmin) {
      menuItems.push({
        key: "7",
        label: <UnstractPricingMenuLink orgName={orgName} />,
      });
    }

    const handleLogin = () => {
      const baseUrl = getBaseUrl();
      const newURL = baseUrl + "/api/v1/login";
      window.location.href = newURL;
    };

    // Logout

    const handleClick = isLoggedIn ? logout : handleLogin;
    const icon = isLoggedIn ? <LogoutOutlined /> : <LoginOutlined />;
    const label = isLoggedIn ? "Logout" : "Login";

    menuItems.push({
      key: "2",
      label: (
        <Button onClick={handleClick} icon={icon} className="logout-button">
          {label}
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
    shouldDisableRouting,
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
          <CustomLogo
            className="topbar-logo cursor-pointer"
            onClick={() =>
              navigate(`/${sessionDetails?.orgName}/${homePagePath}`)
            }
          />
        ) : (
          // : isAPIHub ? (
          //   APIHubLogo && <APIHubLogo className="topbar-logo" />
          // )
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

CustomLogo.propTypes = {
  onClick: PropTypes.func.isRequired,
  className: PropTypes.string.isRequired,
};

export { TopNavBar };
