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
          type="error"
          showIcon
          className="field-error-alert"
          message={
            rawErrors.length === 1
              ? rawErrors[0]
              : "Multiple validation errors:"
          }
          description={
            rawErrors.length > 1 ? (
              <ul className="field-error-list">
                {rawErrors.map((error, index) => (
                  <li key={`err-${error}-${index}`}>{error}</li>
                ))}
              </ul>
            ) : undefined
          }
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
