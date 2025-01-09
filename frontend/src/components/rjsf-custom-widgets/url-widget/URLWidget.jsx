import { Input } from "antd";
import PropTypes from "prop-types";
import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout";

const URLWidget = (props) => {
  const { id, value, onChange, label, schema, required } = props;
  const description = schema?.description || "";
  const handleURLChange = (event) => {
    onChange(event.target.value);
  };

  return (
    <RjsfWidgetLayout
      label={label}
      description={description}
      required={required}
    >
      <Input type="url" id={id} value={value} onChange={handleURLChange} />
    </RjsfWidgetLayout>
  );
};

URLWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  schema: PropTypes.object.isRequired,
  required: PropTypes.bool,
};

export { URLWidget };
