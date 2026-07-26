import { Space, Tooltip } from "antd";
import { Info } from "lucide-react";
import { Typography } from "@/components/ui/antd-typography";

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
