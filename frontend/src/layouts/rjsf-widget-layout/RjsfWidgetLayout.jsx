import { QuestionCircleOutlined } from "@ant-design/icons";
import { Form, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import "./RjsfWidgetLayout.css";

function RjsfWidgetLayout({ children, label, description, required }) {
  return (
    <Form.Item className="widget-form-item">
      <Typography className="form-item-label">
        {required && <span className="form-item-required">* </span>}
        {label}
        {description?.length > 0 && (
          <Tooltip title={description}>
            <QuestionCircleOutlined className="form-item-tooltip" />
          </Tooltip>
        )}
      </Typography>
      {children}
    </Form.Item>
  );
}

RjsfWidgetLayout.propTypes = {
  children: PropTypes.oneOfType([PropTypes.node, PropTypes.element]),
  label: PropTypes.string.isRequired,
  description: PropTypes.string,
  required: PropTypes.bool,
};

export { RjsfWidgetLayout };
