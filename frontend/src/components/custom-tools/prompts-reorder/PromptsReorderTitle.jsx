import { Info } from "lucide-react";
import { Space } from "@/components/ui/shims/antd-layout";
import { Tooltip } from "@/components/ui/shims/antd-overlays";
import { Typography } from "@/components/ui/shims/antd-typography";

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
