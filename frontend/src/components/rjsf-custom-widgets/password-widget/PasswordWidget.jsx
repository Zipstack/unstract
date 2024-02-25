import { Input } from "antd";
import PropTypes from "prop-types";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

const PasswordWidget = ({ id, value, onChange, label, schema, required }) => {
  const description = schema?.description || "";
  const handlePasswordChange = (event) => {
    onChange(event.target.value);
  };

  return (
    <RjsfWidgetLayout
      label={label}
      description={description}
      required={required}
    >
      <Input.Password id={id} value={value} onChange={handlePasswordChange} />
    </RjsfWidgetLayout>
  );
};

PasswordWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  schema: PropTypes.object.isRequired,
  required: PropTypes.bool,
};

export { PasswordWidget };
