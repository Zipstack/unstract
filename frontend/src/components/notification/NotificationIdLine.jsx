import { Typography } from "antd";
import PropTypes from "prop-types";

function NotificationIdLine({ label, value, stacked = false }) {
  if (!value) {
    return null;
  }
  const className = stacked
    ? "notification-id-line notification-id-line--stacked"
    : "notification-id-line";
  return (
    <div className={className}>
      <Typography.Text type="secondary">{label}:</Typography.Text>
      <Typography.Text
        code
        copyable={{ text: value }}
        className="notification-id-line__value"
      >
        {value}
      </Typography.Text>
    </div>
  );
}

NotificationIdLine.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.string,
  stacked: PropTypes.bool,
};

export { NotificationIdLine };
