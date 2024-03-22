import { Alert, Button, Col, Dropdown, Image, Row, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { UnstractLogo } from "../../../assets/index.js";
import {
  getBaseUrl,
  onboardCompleted,
} from "../../../helpers/GetStaticData.js";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import useLogout from "../../../hooks/useLogout.js";
import "../../../layouts/page-layout/PageLayout.css";
import { useSessionStore } from "../../../store/session-store.js";
import "./TopNavBar.css";
import { useAlertStore } from "../../../store/alert-store.js";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal.jsx";
import axios from "axios";

let TrialDaysInfo;
try {
  TrialDaysInfo =
    require("../../../plugins/subscription/trial-helper/TrialDaysInfo.jsx").default;
} catch (err) {
  // Plugin not found
}

function TopNavBar() {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const { orgName, remainingTrialDays, allOrganization, orgId } =
    sessionDetails;
  const baseUrl = getBaseUrl();
  const onBoardUrl = baseUrl + `/${orgName}/onboard`;
  const logout = useLogout();
  const axiosPrivate = useAxiosPrivate();
  const setAlertDetails = useAlertStore();
  const [showOnboardBanner, setShowOnboardBanner] = useState(false);

  useEffect(() => {
    getAdapters();
  }, []);

  const getAdapters = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        const adapterTypes = [
          ...new Set(data?.map((obj) => obj?.adapter_type.toLowerCase())),
        ];
        if (!onboardCompleted(adapterTypes)) {
          setShowOnboardBanner(true);
        }
      })
      .catch((err) => {});
  };

  const cascadeOptions = allOrganization.map((org) => {
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
    await axios(requestOptions);
    window.location.reload();
  };

  // Dropdown items
  const items = [
    {
      key: "1",
      label: (
        <Button
          onClick={() => navigate(`/${orgName}/profile`)}
          className="logout-button"
        >
          Profile
        </Button>
      ),
    },
    {
      key: "2",
      label: (
        <Button onClick={logout} className="logout-button">
          Logout
        </Button>
      ),
    },
    allOrganization.length > 1 && {
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
          <div>Switch Org</div>
        </Dropdown>
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
      <Col span={4}>
        <UnstractLogo className="topbar-logo" />
      </Col>
      <Col span={16} className="top-nav-alert-col">
        {showOnboardBanner && (
          <Alert
            type="error"
            message={
              <>
                <span className="top-nav-alert-msg">
                  Your setup process is incomplete. Now, that&apos;s a bummer!
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
          {TrialDaysInfo && (
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
        </Row>
      </Col>
    </Row>
  );
}

export { TopNavBar };
