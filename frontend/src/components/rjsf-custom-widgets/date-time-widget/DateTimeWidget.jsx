import { DatePicker } from "antd";
import moment from "moment";
import PropTypes from "prop-types";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

const DateTimeWidget = ({ id, value, onChange, label, required }) => {
  const handleDateTimeChange = (dateTime) => {
    onChange(dateTime?.toISOString());
  };

  return (
    <RjsfWidgetLayout label={label} required={required}>
      <DatePicker
        showTime
        id={id}
        value={value ? moment(value) : null}
        onChange={handleDateTimeChange}
      />
    </RjsfWidgetLayout>
  );
};

DateTimeWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  required: PropTypes.bool,
};

export { DateTimeWidget };
