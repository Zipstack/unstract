import { memo } from "react";
import PropTypes from "prop-types";
import {
  CloseOutlined,
  FullscreenOutlined,
  ShrinkOutlined,
} from "@ant-design/icons";
import { Button, Space, Tag, Typography } from "antd";

export const LogsHeader = memo(function LogsHeader({
  isMinimized,
  errorCount,
  onSemiExpand,
  onFullExpand,
  onMinimize,
}) {
  const semiIcon = <ShrinkOutlined />;
  const fullIcon = <FullscreenOutlined />;
  const minimizeIcon = <CloseOutlined />;

  return (
    <div className="logs-header-container">
      <Space>
        <Typography.Text>Logs</Typography.Text>
        {isMinimized && errorCount > 0 && <Tag color="red">{errorCount}</Tag>}
      </Space>
      <Space>
        <Button
          type="text"
          size="small"
          icon={semiIcon}
          onClick={onSemiExpand}
        />
        <Button
          type="text"
          size="small"
          icon={fullIcon}
          onClick={onFullExpand}
        />
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
  errorCount: PropTypes.number.isRequired,
  onSemiExpand: PropTypes.func.isRequired,
  onFullExpand: PropTypes.func.isRequired,
  onMinimize: PropTypes.func.isRequired,
};
