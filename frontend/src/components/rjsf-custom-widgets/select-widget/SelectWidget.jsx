import { Form, Select } from "antd";
import PropTypes from "prop-types";

const { Option } = Select;
const SelectWidget = (props) => {
  const { id, value, options, onChange, rawErrors } = props;
  const handleSelectChange = (selectedValue) => {
    onChange(selectedValue);
  };
  const hasError = rawErrors && rawErrors.length > 0;

  return (
    <Form.Item
      style={{ width: "100%" }}
      validateStatus={hasError ? "error" : ""}
    >
      <Select id={id} value={value} onChange={handleSelectChange} showSearch>
        {options?.enumOptions &&
          options.enumOptions.map((option, index) => (
            <Option key={option.value} value={option.value}>
              {option.label}
            </Option>
          ))}
      </Select>
    </Form.Item>
  );
};

SelectWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  options: PropTypes.any,
  onChange: PropTypes.func.isRequired,
  rawErrors: PropTypes.array,
};

export { SelectWidget };
