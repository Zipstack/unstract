import PropTypes from "prop-types";

import "./FooterLayout.css";

function FooterLayout({ children }) {
  return (
    <div className="tool-ide-main-footer-layout display-flex-right">
      {children}
    </div>
  );
}

FooterLayout.propTypes = {
  children: PropTypes.any.isRequired,
};

export { FooterLayout };
