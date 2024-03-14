import PropTypes from "prop-types";

import "./IslandLayout.css";

function IslandLayout({ children }) {
  return <div className="island-layout">{children}</div>;
}

IslandLayout.propTypes = {
  children: PropTypes.oneOfType([PropTypes.node, PropTypes.element]),
};

export { IslandLayout };
