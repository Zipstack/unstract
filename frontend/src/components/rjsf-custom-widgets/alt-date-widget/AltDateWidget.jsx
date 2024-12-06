import { DatePicker } from "antd";
import moment from "moment";
import PropTypes from "prop-types";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

const AltDateWidget = ({ id, value, onChange, label, schema, required }) => {
  const description = schema?.description || "";

  const handleDateChange = (date) => {
    onChange(date?.toISOString());
  };

  return (
    <RjsfWidgetLayout
      label={label}
      description={description}
      required={required}
    >
      <DatePicker
        id={id}
        value={value ? moment(value) : null}
        onChange={handleDateChange}
      />
    </RjsfWidgetLayout>
  );
};

AltDateWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  schema: PropTypes.object.isRequired,
  required: PropTypes.bool,
};

export { AltDateWidget };
