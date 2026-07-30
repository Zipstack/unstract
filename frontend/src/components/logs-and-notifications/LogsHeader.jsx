import { ChevronDown, ChevronUp, X } from "lucide-react";
import PropTypes from "prop-types";
import { memo } from "react";
import { Button } from "@/components/ui/shims/antd-button";
import { Space } from "@/components/ui/shims/antd-layout";
import { Tag } from "@/components/ui/shims/antd-leaves";
import { Typography } from "@/components/ui/shims/antd-typography";

export const LogsHeader = memo(function LogsHeader({
  isMinimized,
  isFull,
  errorCount,
  onToggleExpand,
  onMinimize,
}) {
  const expandCollapseIcon = isFull ? <ChevronDown /> : <ChevronUp />;

  const minimizeIcon = <X />;

  return (
    <div className="logs-header-container">
      <Space>
        <Typography.Text>Logs</Typography.Text>
        {isMinimized && errorCount > 0 && <Tag color="red">{errorCount}</Tag>}
      </Space>
      <Space>
        <Button type="text" size="small" onClick={onToggleExpand}>
          {expandCollapseIcon}
        </Button>

        <Button
          type="text"
          size="small"
          icon={minimizeIcon}
          onClick={onMinimize}
        />
      </Space>
    </div>
  );
});

LogsHeader.propTypes = {
  isMinimized: PropTypes.bool.isRequired,
  isFull: PropTypes.bool.isRequired,
  errorCount: PropTypes.number.isRequired,
  onToggleExpand: PropTypes.func.isRequired,
  onMinimize: PropTypes.func.isRequired,
};
