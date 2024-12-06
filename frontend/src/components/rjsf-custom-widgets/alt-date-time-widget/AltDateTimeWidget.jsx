import { DatePicker, TimePicker } from "antd";
import moment from "moment";
import PropTypes from "prop-types";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

const AltDateTimeWidget = ({
  id,
  value,
  onChange,
  label,
  schema,
  required,
}) => {
  const description = schema?.description || "";
  const handleDateChange = (date) => {
    onChange(date?.toISOString());
  };

  const handleTimeChange = (time) => {
    const selectedDate = value ? new Date(value) : new Date();
    selectedDate.setHours(time.hour());
    selectedDate.setMinutes(time.minute());
    onChange(selectedDate.toISOString());
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
      <TimePicker
        value={value ? moment(value) : null}
        onChange={handleTimeChange}
      />
    </RjsfWidgetLayout>
  );
};

AltDateTimeWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  schema: PropTypes.object.isRequired,
  required: PropTypes.bool,
};

export { AltDateTimeWidget };
