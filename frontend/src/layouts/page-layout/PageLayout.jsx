import { LeftOutlined, RightOutlined } from "@ant-design/icons";
import { Button, Layout } from "antd";
import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import PropTypes from "prop-types";
import "./PageLayout.css";

import SideNavBar from "../../components/navigations/side-nav-bar/SideNavBar.jsx";
import { TopNavBar } from "../../components/navigations/top-nav-bar/TopNavBar.jsx";

function PageLayout({ sideBarOptions, topNavBarOptions }) {
  const initialCollapsedValue =
    JSON.parse(localStorage.getItem("collapsed")) || false;
  const [collapsed, setCollapsed] = useState(initialCollapsedValue);
  useEffect(() => {
    localStorage.setItem("collapsed", JSON.stringify(collapsed));
  }, [collapsed]);

  return (
    <div className="landingPage">
      <TopNavBar {...topNavBarOptions} />
      <Layout>
        <SideNavBar collapsed={collapsed} {...sideBarOptions} />
        <Layout>
          <Button
            shape="circle"
            size="small"
            icon={collapsed ? <RightOutlined /> : <LeftOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            className="collapse_btn"
          />
          <Outlet />
        </Layout>
      </Layout>
    </div>
  );
}
PageLayout.propTypes = {
  sideBarOptions: PropTypes.any,
  topNavBarOptions: PropTypes.any,
};

export { PageLayout };
