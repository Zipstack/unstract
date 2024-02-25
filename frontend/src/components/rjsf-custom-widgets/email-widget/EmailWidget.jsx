import { Input } from "antd";
import PropTypes from "prop-types";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

const EmailWidget = ({ id, value, onChange, label, required }) => {
  const handleEmailChange = (event) => {
    onChange(event.target.value);
  };

  return (
    <RjsfWidgetLayout label={label} required={required}>
      <Input type="email" id={id} value={value} onChange={handleEmailChange} />
    </RjsfWidgetLayout>
  );
};

EmailWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  required: PropTypes.bool,
};

export { EmailWidget };
