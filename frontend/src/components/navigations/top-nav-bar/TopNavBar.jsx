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
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { MoonIcon, SunIcon, UnstractLogo } from "../../../assets/index.js";
import { THEME, getBaseUrl } from "../../../helpers/GetStaticData.js";
import useLogout from "../../../hooks/useLogout.js";
import "../../../layouts/page-layout/PageLayout.css";
import { useSessionStore } from "../../../store/session-store.js";
import "./TopNavBar.css";

// const PREFERS_DARK_THEME = window.matchMedia("(prefers-color-scheme: dark)");

function TopNavBar() {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const { orgName, adapters } = sessionDetails;
  const updateSessionDetails = useSessionStore(
    (state) => state.updateSessionDetails
  );
  const baseUrl = getBaseUrl();
  const onBoardUrl = baseUrl + `/${orgName}/onboard`;
  const logout = useLogout();

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
      <Col span={8}>
        <UnstractLogo className="topbar-logo" />
      </Col>
      <Col span={8}>
        {adapters.length < 3 && (
          <Alert
            type="error"
            message="Your setup process is incomplete. Now, that's a bummer!"
            showIcon
            action={
              <a
                href={onBoardUrl}
                size="small"
                type="text"
                style={{ textDecoration: "underline" }}
              >
                Complete it to start using Unstract.
              </a>
            }
          />
        )}
      </Col>
      <Col span={8}>
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
