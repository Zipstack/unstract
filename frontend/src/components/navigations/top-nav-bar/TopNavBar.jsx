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
import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import axios from "axios";
import PropTypes from "prop-types";

import { UnstractLogo } from "../../../assets/index.js";
import {
  getBaseUrl,
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
let selectedProduct;
let selectedProductStore;

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

try {
  selectedProductStore = require("../../../plugins/llm-whisperer/store/select-product-store.js");
} catch {
  // Ignore if hook not available
}

let WhispererLogo;
try {
  WhispererLogo =
    require("../../../plugins/assets/llmWhisperer/index.js").WhispererLogo;
} catch {
  // Ignore if hook not available
}

function TopNavBar({ isSimpleLayout }) {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const { orgName, remainingTrialDays, allOrganization, orgId } =
    sessionDetails;
  const baseUrl = getBaseUrl();
  const onBoardUrl = baseUrl + `/${orgName}/onboard`;
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

  useEffect(() => {
    const isUnstractReviewer = sessionDetails.role === "unstract_reviewer";
    const isUnstractSupervisor = sessionDetails.role === "unstract_supervisor";
    const isUnstractAdmin = sessionDetails.role === "unstract_admin";

    setShowOnboardBanner(
      !onboardCompleted(sessionDetails?.adapters) &&
        !isUnstractReviewer &&
        !isUnstractSupervisor
    );

    setApproverStatus(isUnstractAdmin || isUnstractSupervisor);
    setReviewerStatus(isUnstractReviewer);
  }, [sessionDetails]);

  useEffect(() => {
    const checkReviewPage = location.pathname.split("review");
    if (checkReviewPage.length > 1) {
      if (checkReviewPage[1].includes("/approve")) {
        setReviewPageHeader("Approve");
      } else if (checkReviewPage[1].includes("/download_and_sync")) {
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

  const cascadeOptions = allOrganization?.map((org) => {
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
            content={`Want to switch to ${org?.display_name} `}
          >
            <div>{org?.display_name}</div>
          </ConfirmModal>
        ),
    };
  });

  const handleContinue = async (selectedOrg) => {
    const requestOptions = {
      method: "POST",
      url: `/api/v1/organization/${selectedOrg}/set`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    await axios(requestOptions)
      .then(() => {
        navigate("/");
        window.location.reload();
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  // Profile Dropdown items
  const items = [
    isUnstract && {
      key: "1",
      label: (
        <Button
          onClick={() => navigate(`/${orgName}/profile`)}
          className="logout-button"
        >
          <UserOutlined /> Profile
        </Button>
      ),
    },
    allOrganization?.length > 1 && {
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
            {" "}
            <UserSwitchOutlined /> Switch Org
          </div>
        </Dropdown>
      ),
    },
    isUnstract &&
      (reviewerStatus || approverStatus) && {
        key: "4",
        label: (
          <Button
            onClick={() => navigate(`/${orgName}/review`)}
            className="logout-button"
          >
            <FileProtectOutlined /> Review
          </Button>
        ),
      },
    isUnstract &&
      approverStatus && {
        key: "5",
        label: (
          <Button
            onClick={() => navigate(`/${orgName}/review/approve`)}
            className="logout-button"
          >
            <LikeOutlined /> Approve
          </Button>
        ),
      },
    isUnstract &&
      approverStatus && {
        key: "6",
        label: (
          <Button
            onClick={() => navigate(`/${orgName}/review/download_and_sync`)}
            className="logout-button"
          >
            <DownloadOutlined /> Download and Sync Manager
          </Button>
        ),
      },
    {
      key: "2",
      label: (
        <Button onClick={logout} className="logout-button">
          <LogoutOutlined /> Logout
        </Button>
      ),
    },
  ];

  // Function to get the initials from the user name
  const getInitials = (name) => {
    const names = name?.split(" ");
    const initials = names
      ?.map((n) => n.charAt(0))
      ?.join("")
      ?.toUpperCase();
    return initials;
  };

  return (
    <Row align="middle" className="topNav">
      <Col span={6} className="platform-switch-container">
        {isUnstract ? (
          <UnstractLogo className="topbar-logo" />
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
      {!isSimpleLayout && (
        <>
          <Col span={14} className="top-nav-alert-col">
            {isUnstract && showOnboardBanner && (
              <Alert
                type="error"
                message={
                  <>
                    <span className="top-nav-alert-msg">
                      Your setup process is incomplete. Now, that&apos;s a
                      bummer!
                    </span>
                    <a
                      href={onBoardUrl}
                      size="small"
                      type="text"
                      className="top-nav-alert-link"
                    >
                      Complete it to start using Unstract
                    </a>
                  </>
                }
                showIcon
              />
            )}
          </Col>
          <Col span={4}>
            <Row justify="end" align="middle">
              <Space>
                {isUnstract && TrialDaysInfo && (
                  <TrialDaysInfo remainingTrialDays={remainingTrialDays} />
                )}
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
        </>
      )}
    </Row>
  );
}

TopNavBar.propTypes = {
  isSimpleLayout: PropTypes.bool,
};

export { TopNavBar };
