import { Layout } from "@/components/ui/antd-structure";
import "./FullPageLayout.css";

import { LazyOutlet } from "../../components/error/LazyOutlet/LazyOutlet.jsx";

function FullPageLayout() {
  return (
    <Layout className="container">
      <LazyOutlet />
    </Layout>
  );
}

export { FullPageLayout };
