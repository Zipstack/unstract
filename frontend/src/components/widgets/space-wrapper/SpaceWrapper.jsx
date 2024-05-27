import { Space } from "antd";
import PropTypes from "prop-types";

const SpaceWrapper = ({ children, direction = "vertical" }) => {
  return (
    <Space direction={direction} className="width-100">
      {children}
    </Space>
  );
};

SpaceWrapper.propTypes = {
  children: PropTypes.any,
  direction: PropTypes.string,
};

export default SpaceWrapper;
