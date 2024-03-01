import {
  Alert,
  Button,
  Col,
  Dropdown,
  Image,
  Row,
  Switch,
  Typography,
} from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { MoonIcon, SunIcon, UnstractLogo } from "../../../assets/index.js";
import {
  THEME,
  getBaseUrl,
  onboardCompleted,
} from "../../../helpers/GetStaticData.js";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import useLogout from "../../../hooks/useLogout.js";
import "../../../layouts/page-layout/PageLayout.css";
import { useSessionStore } from "../../../store/session-store.js";
import "./TopNavBar.css";

// const PREFERS_DARK_THEME = window.matchMedia("(prefers-color-scheme: dark)");

function TopNavBar() {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const { orgName } = sessionDetails;
  const updateSessionDetails = useSessionStore(
    (state) => state.updateSessionDetails
  );
  const baseUrl = getBaseUrl();
  const onBoardUrl = baseUrl + `/${orgName}/onboard`;
  const logout = useLogout();
  const axiosPrivate = useAxiosPrivate();
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
          ...new Set(data?.map((obj) => obj.adapter_type.toLowerCase())),
        ];
        if (!onboardCompleted(adapterTypes)) {
          setShowOnboardBanner(true);
        }
      })
      .catch((err) => {})
      .finally(() => {});
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
  ];

  useEffect(() => {
    // if (PREFERS_DARK_THEME.matches) {
    //   document.body.classList.add(THEME.DARK);
    //   updateTheme(THEME.DARK);
    // }
    updateTheme(THEME.LIGHT);
  }, []);

  function updateTheme(theme = THEME.LIGHT) {
    updateSessionDetails({ currentTheme: theme });
  }

  function changeTheme(checked) {
    if (checked) {
      document.body.classList.add(THEME.DARK);
    } else {
      document.body.classList.remove(THEME.DARK);
    }
    updateTheme(checked ? THEME.DARK : THEME.LIGHT);
  }
  // Function to get the initials from the user name
  const getInitials = (name) => {
    const names = name.split(" ");
    const initials = names
      .map((n) => n.charAt(0))
      .join("")
      .toUpperCase();
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
          <Col>
            <Switch
              onClick={changeTheme}
              // checked={currentTheme === THEME.LIGHT}
              checked={false}
              checkedChildren={<MoonIcon />}
              unCheckedChildren={<SunIcon />}
              disabled
            />
          </Col>
          <Col style={{ marginLeft: "15px" }}>
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
          </Col>
        </Row>
      </Col>
    </Row>
  );
}

export { TopNavBar };
