import PropTypes from "prop-types";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

const HiddenWidget = ({ id, value, label }) => {
  return (
    <RjsfWidgetLayout label={label}>
      <input type="hidden" id={id} value={value} />
    </RjsfWidgetLayout>
  );
};

HiddenWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.any,
  label: PropTypes.string.isRequired,
};

export { HiddenWidget };
