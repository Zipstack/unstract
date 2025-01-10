import PropTypes from "prop-types";
import { Checkbox } from "antd";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

const CheckboxesWidget = ({
  id,
  options,
  value,
  onChange,
  label,
  schema,
  required,
  readonly,
}) => {
  const description = schema?.description || "";
  const handleCheckboxChange = (optionValue) => {
    const newValue = [...(value || [])];
    const index = newValue.indexOf(optionValue);
    if (index === -1) {
      newValue.push(optionValue);
    } else {
      newValue.splice(index, 1);
    }
    onChange(newValue);
  };

  return (
    <RjsfWidgetLayout
      label={label}
      description={description}
      required={required}
    >
      {options.map((option) => (
        <Checkbox
          key={option.value}
          checked={value?.includes(option.value)}
          onChange={() => handleCheckboxChange(option.value)}
          disabled={readonly}
        >
          {option.label}
        </Checkbox>
      ))}
    </RjsfWidgetLayout>
  );
};

CheckboxesWidget.propTypes = {
  id: PropTypes.string.isRequired,
  options: PropTypes.arrayOf(PropTypes.object).isRequired,
  value: PropTypes.array,
  onChange: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  schema: PropTypes.object.isRequired,
  required: PropTypes.bool,
  readonly: PropTypes.bool.isRequired,
};

export { CheckboxesWidget };
