import { ArrowLeftOutlined, EditOutlined } from "@ant-design/icons";
import { Button, Typography } from "antd";
import { useNavigate } from "react-router-dom";

import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import "./HeaderTitle.css";

function HeaderTitle() {
  const navigate = useNavigate();
  const { details } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();

  return (
    <div className="custom-tools-header">
      <div>
        <Button
          size="small"
          type="text"
          onClick={() => navigate(`/${sessionDetails?.orgName}/tools`)}
        >
          <ArrowLeftOutlined />
        </Button>
      </div>
      <div>
        <Typography.Text className="custom-tools-name" strong>
          {details?.tool_name}
        </Typography.Text>
        <Button size="small" type="text" disabled>
          <EditOutlined />
        </Button>
      </div>
    </div>
  );
}
export { HeaderTitle };
