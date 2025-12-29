import { ExclamationCircleOutlined } from "@ant-design/icons";
import { Alert, Button, Space } from "antd";
import PropTypes from "prop-types";
import "./ExportReminderBar.css";

function ExportReminderBar({ message, onExport, isExporting }) {
  return (
    <div className="export-reminder-bar">
      <Alert
        message={
          <Space className="export-reminder-content">
            <ExclamationCircleOutlined />
            <span className="export-reminder-text">{message}</span>
            <Button
              type="primary"
              size="small"
              onClick={onExport}
              loading={isExporting}
              className="export-reminder-button"
            >
              Export Now
            </Button>
          </Space>
        }
        type="warning"
        banner
        closable={false}
      />
    </div>
  );
}

ExportReminderBar.propTypes = {
  message: PropTypes.string.isRequired,
  onExport: PropTypes.func.isRequired,
  isExporting: PropTypes.bool,
};

ExportReminderBar.defaultProps = {
  isExporting: false,
};

export { ExportReminderBar };
