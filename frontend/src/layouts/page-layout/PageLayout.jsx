import { Layout } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import "./PageLayout.css";

import { LazyOutlet } from "../../components/error/LazyOutlet/LazyOutlet.jsx";
import { DisplayLogsAndNotifications } from "../../components/logs-and-notifications/DisplayLogsAndNotifications.jsx";
import SideNavBar from "../../components/navigations/side-nav-bar/SideNavBar.jsx";
import { TopNavBar } from "../../components/navigations/top-nav-bar/TopNavBar.jsx";
import {
  getLocalStorageValue,
  setLocalStorageValue,
} from "../../helpers/localStorage";
import { isModuleMissing } from "../../helpers/pluginLoader.js";

// Optional status banner contributed by the marketplace plugin, when
// present. The plugin is absent in OSS builds — the import fails and
// nothing is mounted. The banner self-manages its visibility.
let MarketplacePendingBanner;
try {
  const marketplaceMod = await import("../../plugins/marketplace");
  MarketplacePendingBanner = marketplaceMod.MarketplacePendingBanner;
} catch (err) {
  // Missing plugin is the expected case; surface anything else so a
  // broken plugin doesn't silently unmount its UI.
  if (!isModuleMissing(err)) {
    // eslint-disable-next-line no-console
    console.error(
      "[marketplace] MarketplacePendingBanner import failed unexpectedly",
      err,
    );
  }
}

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
