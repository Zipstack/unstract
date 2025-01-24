import { memo } from "react";
import PropTypes from "prop-types";
import {
  CloseOutlined,
  FullscreenOutlined,
  ShrinkOutlined,
} from "@ant-design/icons";
import { Button, Space, Typography } from "antd";

export const LogsHeader = memo(function LogsHeader({
  onSemiExpand,
  onFullExpand,
  onMinimize,
}) {
  const semiIcon = <ShrinkOutlined />;
  const fullIcon = <FullscreenOutlined />;
  const minimizeIcon = <CloseOutlined />;

  return (
    <div className="logs-header-container">
      <Typography.Text>Logs</Typography.Text>
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
  onSemiExpand: PropTypes.func.isRequired,
  onFullExpand: PropTypes.func.isRequired,
  onMinimize: PropTypes.func.isRequired,
};
