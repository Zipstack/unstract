import { Button } from "antd";
import PropTypes from "prop-types";

import "./CustomButton.css";

function CustomButton({ ...props }) {
  const { type } = props;

  return (
    <Button
      className={type === "primary" ? "custom-button-primary" : ""}
      {...props}
    />
  );
}

CustomButton.propTypes = {
  type: PropTypes.string,
  disabled: PropTypes.bool,
};

export { CustomButton };
