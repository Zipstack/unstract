import { Switch, Button, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";
import "./LogsRefreshControls.css";

function LogsRefreshControls({ autoRefresh, setAutoRefresh, onRefresh }) {
  return (
    <div className="logs-refresh-controls">
      <Typography.Text className="logs-auto-refresh-label">
        Auto-refresh (30s)
      </Typography.Text>
      <Switch size="small" checked={autoRefresh} onChange={setAutoRefresh} />
      <Button
        icon={<ReloadOutlined />}
        onClick={onRefresh}
        className="logs-refresh-btn"
      >
        Refresh
      </Button>
    </div>
  );
}

LogsRefreshControls.propTypes = {
  autoRefresh: PropTypes.bool.isRequired,
  setAutoRefresh: PropTypes.func.isRequired,
  onRefresh: PropTypes.func.isRequired,
};

export { LogsRefreshControls };
