import { Space } from "antd";
import PropTypes from "prop-types";

const SpaceWrapper = ({ children }) => {
  return (
    <Space direction="vertical" className="width-100">
      {children}
    </Space>
  );
};

SpaceWrapper.propTypes = {
  children: PropTypes.any,
};

export default SpaceWrapper;
