import PropTypes from "prop-types";
import { Input } from "antd";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

const ColorWidget = ({ id, value, onChange, schema, label, required }) => {
  const description = schema?.description || "";

  const handleColorChange = (event) => {
    onChange(event.target.value);
  };

  return (
    <RjsfWidgetLayout
      label={label}
      description={description}
      required={required}
    >
      <Input type="color" id={id} value={value} onChange={handleColorChange} />
    </RjsfWidgetLayout>
  );
};

ColorWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  schema: PropTypes.object.isRequired,
  label: PropTypes.string.isRequired,
  required: PropTypes.bool,
};

export { ColorWidget };
