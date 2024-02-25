import { InputNumber } from "antd";
import PropTypes from "prop-types";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

const UpDownWidget = ({ id, value, onChange, label, required }) => {
  const handleNumberChange = (numberValue) => {
    onChange(numberValue);
  };

  return (
    <RjsfWidgetLayout label={label} required={required}>
      <InputNumber id={id} value={value} onChange={handleNumberChange} />
    </RjsfWidgetLayout>
  );
};

UpDownWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.number,
  onChange: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  required: PropTypes.bool,
};

export { UpDownWidget };
