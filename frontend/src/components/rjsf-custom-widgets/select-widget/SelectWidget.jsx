import { Form, Select, Space, Typography } from "antd";
import PropTypes from "prop-types";

import CustomMarkdown from "../../helpers/custom-markdown/CustomMarkdown";

const { Option } = Select;
const SelectWidget = (props) => {
  const { id, value, options, onChange, label, schema, rawErrors, readonly } =
    props;
  const description = schema?.description || "";

  const handleSelectChange = (selectedValue) => {
    onChange(selectedValue);
  };
  const hasError = rawErrors && rawErrors.length > 0;

  return (
    <Form.Item className="width-100" validateStatus={hasError ? "error" : ""}>
      <Space direction="vertical" className="width-100">
        <Typography.Text>{label}</Typography.Text>
        <div>
          <Select
            id={id}
            value={value}
            onChange={handleSelectChange}
            showSearch
            disabled={readonly}
          >
            {options?.enumOptions &&
              options.enumOptions.map((option, index) => (
                <Option key={option.value} value={option.value}>
                  {option.label}
                </Option>
              ))}
          </Select>
          {description?.length > 0 && (
            <CustomMarkdown
              text={description}
              isSecondary={true}
              styleClassName="rjsf-helper-font"
            />
          )}
        </div>
      </Space>
    </Form.Item>
  );
};

SelectWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  options: PropTypes.any,
  onChange: PropTypes.func.isRequired,
  rawErrors: PropTypes.array,
  label: PropTypes.string.isRequired,
  schema: PropTypes.object.isRequired,
  readonly: PropTypes.bool.isRequired,
};

export { SelectWidget };
