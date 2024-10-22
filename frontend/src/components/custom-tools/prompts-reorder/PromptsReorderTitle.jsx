import { InfoCircleOutlined } from "@ant-design/icons";
import { Space, Tooltip, Typography } from "antd";

function PromptsReorderTitle() {
  return (
    <Space>
      <Typography.Text>Reorder Prompts</Typography.Text>
      <Tooltip title="Drag and drop the prompts to arrange them in your desired order.">
        <InfoCircleOutlined />
      </Tooltip>
    </Space>
  );
}

export { PromptsReorderTitle };
