import { Space, Tooltip, Typography } from "antd";
import { Info } from "lucide-react";

function PromptsReorderTitle() {
  return (
    <Space>
      <Typography.Text>Reorder Prompts</Typography.Text>
      <Tooltip title="Drag and drop the prompts to arrange them in your desired order.">
        <Info />
      </Tooltip>
    </Space>
  );
}

export { PromptsReorderTitle };
