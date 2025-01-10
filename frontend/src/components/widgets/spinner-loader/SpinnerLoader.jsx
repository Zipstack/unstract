import { Spin } from "antd";
import PropTypes from "prop-types";

import "./SpinnerLoader.css";

const SPINNER_SIZE = {
  SMALL: "small",
  LARGE: "large",
};
const SPINNER_ALIGNMENT = {
  DEFAULT: "default",
};

function SpinnerLoader({
  size = "default",
  delay = 0,
  text = "",
  align = "center",
}) {
  return (
    <div className="width-100 height-100">
      <div
        className={`spinner-loader-layout ${
          align === SPINNER_ALIGNMENT.DEFAULT ? "" : "center"
        }`}
      >
        <Spin delay={delay} tip={text} size={size} />
      </div>
    </div>
  );
}

SpinnerLoader.propTypes = {
  size: PropTypes.string,
  delay: PropTypes.number,
  text: PropTypes.string,
  align: PropTypes.string,
};

export { SPINNER_ALIGNMENT, SPINNER_SIZE, SpinnerLoader };
