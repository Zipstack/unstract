import PropTypes from "prop-types";
import { Tag } from "antd";

import { getStatusColor, getStatusText } from "../utils/helpers";

const StatusBadge = ({ status }) => {
  if (!status) return null;

  const color = getStatusColor(status);
  const text = getStatusText(status);

  return <Tag color={color}>{text}</Tag>;
};

StatusBadge.propTypes = {
  status: PropTypes.string,
};

export default StatusBadge;
