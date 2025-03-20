import { memo } from "react";
import PropTypes from "prop-types";
import { CloseOutlined, DownOutlined, UpOutlined } from "@ant-design/icons";
import { Button, Space, Tag, Typography } from "antd";

export const LogsHeader = memo(function LogsHeader({
  isMinimized,
  isFull,
  errorCount,
  onToggleExpand,
  onMinimize,
}) {
  const expandCollapseIcon = isFull ? <DownOutlined /> : <UpOutlined />;

  const minimizeIcon = <CloseOutlined />;

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
