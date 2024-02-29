import { Typography } from "antd";
import PropTypes from "prop-types";
import "./GridLayout.css";

function GridLayout({ children, title }) {
  return (
    <div className="grid-layout">
      <div className="grid-layout-title">
        <Typography.Text strong>{title}</Typography.Text>
      </div>
      <div className="grid-layout-main">{children}</div>
    </div>
  );
}

GridLayout.propTypes = {
  children: PropTypes.any,
  title: PropTypes.string,
};

export { GridLayout };
