import PropTypes from "prop-types";
import "../settings/Settings.css";

function SettingsLayout({ children }) {
  return (
    <div className="settings-container">
      <main className="settings-content" role="main">
        {children}
      </main>
    </div>
  );
}

SettingsLayout.propTypes = {
  children: PropTypes.node.isRequired,
};

export { SettingsLayout };
