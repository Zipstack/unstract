import { Layout } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import "./PageLayout.css";

import { DisplayLogsAndNotifications } from "../../components/logs-and-notifications/DisplayLogsAndNotifications.jsx";
import SideNavBar from "../../components/navigations/side-nav-bar/SideNavBar.jsx";
import { TopNavBar } from "../../components/navigations/top-nav-bar/TopNavBar.jsx";
import {
  getLocalStorageValue,
  setLocalStorageValue,
} from "../../helpers/localStorage";

function PageLayout({
  sideBarOptions,
  topNavBarOptions,
  showLogsAndNotifications = true,
  hideSidebar = false,
}) {
  const [collapsed, setCollapsed] = useState(() =>
    getLocalStorageValue("collapsed", false),
  );
  useEffect(() => {
    setLocalStorageValue("collapsed", collapsed);
  }, [collapsed]);
  return (
    <div className="landingPage">
      <TopNavBar topNavBarOptions={topNavBarOptions} />
      <Layout>
        {!hideSidebar && (
          <SideNavBar
            collapsed={collapsed}
            setCollapsed={setCollapsed}
            {...sideBarOptions}
          />
        )}
        <Layout>
          <Outlet />
          {!hideSidebar && <div className="height-40" />}
          {showLogsAndNotifications && <DisplayLogsAndNotifications />}
        </Layout>
      </Layout>
    </div>
  );
}
PageLayout.propTypes = {
  sideBarOptions: PropTypes.any,
  topNavBarOptions: PropTypes.any,
  showLogsAndNotifications: PropTypes.bool,
  hideSidebar: PropTypes.bool,
};

export { PageLayout };
