import { Switch, Tooltip } from "antd";
import { RotateCw } from "lucide-react";
import PropTypes from "prop-types";
import { Button } from "@/components/ui/antd-button";
import { Typography } from "@/components/ui/typography";
import "./LogsRefreshControls.css";

function LogsRefreshControls({
  autoRefresh,
  setAutoRefresh,
  onRefresh,
  disabled = false,
}) {
  return (
    <Tooltip title={disabled ? "Execution has completed" : ""}>
      <div className={`logs-refresh-controls ${disabled ? "disabled" : ""}`}>
        <Typography.Text className="logs-auto-refresh-label">
          Auto-refresh (30s)
        </Typography.Text>
        <Switch
          size="small"
          checked={autoRefresh}
          onChange={setAutoRefresh}
          disabled={disabled}
        />
        <Button
          icon={<RotateCw />}
          onClick={onRefresh}
          className="logs-refresh-btn"
          disabled={disabled}
        >
          Refresh
        </Button>
      </div>
    </Tooltip>
  );
}

LogsRefreshControls.propTypes = {
  autoRefresh: PropTypes.bool.isRequired,
  setAutoRefresh: PropTypes.func.isRequired,
  onRefresh: PropTypes.func.isRequired,
  disabled: PropTypes.bool,
};

export { LogsRefreshControls };
