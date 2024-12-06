import PropTypes from "prop-types";

const CustomFieldTemplate = (props) => {
  const { classNames, errors, children, help } = props;
  return (
    <div className={classNames}>
      {children}
      {errors}
      {help}
    </div>
  );
};

CustomFieldTemplate.propTypes = {
  classNames: PropTypes.string,
  help: PropTypes.node,
  errors: PropTypes.node,
  children: PropTypes.node,
};

export { CustomFieldTemplate };
