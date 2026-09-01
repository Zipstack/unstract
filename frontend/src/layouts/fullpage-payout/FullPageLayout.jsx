import { Layout } from "@/components/ui/shims/antd-structure";
import "./FullPageLayout.css";

import { LazyOutlet } from "../../components/error/LazyOutlet/LazyOutlet.jsx";

function FullPageLayout() {
  return (
    <Layout className="full-page-layout">
      <LazyOutlet />
    </Layout>
  );
}

export { FullPageLayout };
