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
import { isModuleMissing } from "../../helpers/pluginLoader.js";

// Marketplace pending-purchase banner (cloud plugin). Shows "your
// marketplace purchase is being confirmed" between the buyer's claim and
// the provisioning webhook, and clears itself once the subscription
// activates. Absent in OSS builds — the import fails and the banner
// stays unmounted.
let MarketplacePendingBanner;
try {
  const marketplaceMod = await import("../../plugins/marketplace");
  MarketplacePendingBanner = marketplaceMod.MarketplacePendingBanner;
} catch (err) {
  // Expected in OSS builds where the cloud plugin is absent; anything
  // else (a broken plugin) must surface rather than silently removing
  // the pending-purchase UX in cloud builds.
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
