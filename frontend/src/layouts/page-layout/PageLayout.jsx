import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { Layout } from "@/components/ui/shims/antd-structure";
import "./PageLayout.css";

import { LazyOutlet } from "../../components/error/LazyOutlet/LazyOutlet.jsx";
import { DisplayLogsAndNotifications } from "../../components/logs-and-notifications/DisplayLogsAndNotifications.jsx";
import SideNavBar from "../../components/navigations/side-nav-bar/SideNavBar.jsx";
import { TopNavBar } from "../../components/navigations/top-nav-bar/TopNavBar.jsx";
import {
  getLocalStorageValue,
  setLocalStorageValue,
} from "../../helpers/localStorage";
import { loadPlugin } from "../../helpers/pluginLoader.js";

// Optional status banner contributed by the marketplace plugin, when
// present. The plugin is absent in OSS builds, so nothing is mounted. The
// banner self-manages its visibility.
const MarketplacePendingBanner = await loadPlugin(() =>
  import("../../plugins/marketplace").then((m) => m.MarketplacePendingBanner),
);

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
          {MarketplacePendingBanner && <MarketplacePendingBanner />}
          <LazyOutlet />
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
