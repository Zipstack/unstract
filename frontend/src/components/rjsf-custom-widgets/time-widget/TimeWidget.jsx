import { TimePicker } from "antd";
import moment from "moment";
import PropTypes from "prop-types";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

const TimeWidget = ({ id, value, onChange, label, required }) => {
  const handleTimeChange = (time) => {
    onChange(time?.toISOString());
  };

  return (
    <RjsfWidgetLayout label={label} required={required}>
      <TimePicker
        id={id}
        value={value ? moment(value) : null}
        onChange={handleTimeChange}
      />
    </RjsfWidgetLayout>
  );
};

TimeWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  required: PropTypes.bool,
};

export { TimeWidget };
