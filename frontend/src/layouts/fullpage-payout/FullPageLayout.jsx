import { Layout } from "antd";
import { Outlet } from "react-router-dom";
import "./FullPageLayout.css";

function FullPageLayout() {
  return (
    <Layout className="container">
      <Outlet />
    </Layout>
  );
}

export { FullPageLayout };
