import { Space, Tooltip } from "antd";
import { useNavigate } from "react-router-dom";

import { useSessionStore } from "../../../store/session-store";

const customLinkColumn = ({ title, key, tooltip, align }) => {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();

  const column = {
    title: title,
    key: key,
    render: (_, record) => (
      <Tooltip title={tooltip}>
        <Space
          className="workflowName"
          onClick={() =>
            navigate(
              `/${sessionDetails?.orgId}/workflow/${record?.project_id}/agency`
            )
          }
        >
          {record?.workflow_name}
        </Space>
      </Tooltip>
    ),
    align: align,
  };

  return column;
};

export default customLinkColumn;
