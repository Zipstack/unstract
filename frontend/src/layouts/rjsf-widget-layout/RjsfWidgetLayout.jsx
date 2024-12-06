import { Form, Typography } from "antd";
import PropTypes from "prop-types";
import "./RjsfWidgetLayout.css";
import CustomMarkdown from "../../components/helpers/custom-markdown/CustomMarkdown";

function RjsfWidgetLayout({ children, label, description, required }) {
  return (
    <Form.Item className="widget-form-item">
      <Typography className="form-item-label">
        {required && <span className="form-item-required">* </span>}
        {label}
      </Typography>
      {children}
      {description?.length > 0 && (
        <CustomMarkdown
          text={description}
          isSecondary={true}
          styleClassName="rjsf-helper-font"
        />
      )}
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
