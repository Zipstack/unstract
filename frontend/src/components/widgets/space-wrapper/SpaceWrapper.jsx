import PropTypes from "prop-types";
import { Space } from "@/components/ui/shims/antd-layout";

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
