import { Alert } from "antd";
import PropTypes from "prop-types";
import "./CustomFieldTemplate.css";

const CustomFieldTemplate = (props) => {
  const { classNames, children, help, rawErrors } = props;
  const hasErrors = rawErrors && rawErrors.length > 0;

  return (
    <div className={`${classNames} ${hasErrors ? "field-with-errors" : ""}`}>
      {children}
      {hasErrors && (
        <Alert
          message={rawErrors.join(", ")}
          type="error"
          size="small"
          showIcon
          className="field-error-alert"
        />
      )}
      {help}
    </div>
  );
};

CustomFieldTemplate.propTypes = {
  classNames: PropTypes.string,
  help: PropTypes.node,
  children: PropTypes.node,
  rawErrors: PropTypes.array,
};

export { CustomFieldTemplate };
