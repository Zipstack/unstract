import { Button, Space, Typography } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";

import { useSessionStore } from "../../../store/session-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { HeaderPublic } from "../../../plugins/prompt-studio-public-share/header-public/HeaderPublic";

function OutputAnalyzerHeader() {
  const { sessionDetails } = useSessionStore();
  const { id } = useParams();
  const navigate = useNavigate();
  const { isPublicSource } = useCustomToolStore();
  const handleNavigate = () => {
    if (isPublicSource) {
      navigate(-1);
    }
    navigate(`/${sessionDetails?.orgName}/tools/${id}`);
  };
  return (
    <div>
      {isPublicSource && <HeaderPublic />}
      <div className="output-analyzer-header">
        <div>
          <Space>
            <Button size="small" type="text" onClick={handleNavigate}>
              <ArrowLeftOutlined />
            </Button>
            <Typography.Text className="font-size-16" strong>
              Output Analyzer
            </Typography.Text>
          </Space>
        </div>
        <div></div>
      </div>
    </div>
  );
}

export { OutputAnalyzerHeader };
