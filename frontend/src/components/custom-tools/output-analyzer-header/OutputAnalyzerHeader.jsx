import { Button, Space, Typography } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { useSessionStore } from "../../../store/session-store";

function OutputAnalyzerHeader() {
  const { sessionDetails } = useSessionStore();
  const { id } = useParams();
  const navigate = useNavigate();

  return (
    <div className="output-analyzer-header">
      <div>
        <Space>
          <Button
            size="small"
            type="text"
            onClick={() => navigate(`/${sessionDetails?.orgName}/tools/${id}`)}
          >
            <ArrowLeftOutlined />
          </Button>
          <Typography.Text className="font-size-16" strong>
            Output Analyzer
          </Typography.Text>
        </Space>
      </div>
      <div></div>
    </div>
  );
}

export { OutputAnalyzerHeader };
