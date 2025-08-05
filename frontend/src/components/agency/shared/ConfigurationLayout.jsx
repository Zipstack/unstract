import { Typography } from "antd";
import PropTypes from "prop-types";

function ConfigurationLayout({ title, children, className = "" }) {
  return (
    <div className={`conn-modal-flex ${className}`}>
      <Typography.Text strong>{title}</Typography.Text>
      <div className="conn-modal-gap" />
      <div className="conn-modal-flex-1">{children}</div>
    </div>
  );
}

ConfigurationLayout.propTypes = {
  title: PropTypes.string.isRequired,
  children: PropTypes.node.isRequired,
  className: PropTypes.string,
};

export { ConfigurationLayout };
