import { Form, Input } from "antd";
import PropTypes from "prop-types";

const URLWidget = ({ id, value, onChange, rawErrors }) => {
  const handleURLChange = (event) => {
    onChange(event.target.value);
  };

  const hasError = rawErrors && rawErrors.length > 0;

  return (
    <Form.Item
      style={{ width: "100%" }}
      validateStatus={hasError ? "error" : ""}
    >
      <Input type="url" id={id} value={value} onChange={handleURLChange} />
    </Form.Item>
  );
};

URLWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  rawErrors: PropTypes.array,
};

export { URLWidget };
