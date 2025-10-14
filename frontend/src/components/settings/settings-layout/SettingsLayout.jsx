import { useEffect, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import PropTypes from "prop-types";
import "../settings/Settings.css";
import { useSessionStore } from "../../../store/session-store";

function SettingsLayout({ children, activeKey }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [isSidebarVisible, setIsSidebarVisible] = useState(true);
  const sidebarRef = useRef(null);
  const { sessionDetails } = useSessionStore();

  // Guard against missing orgName
  if (!sessionDetails?.orgName) {
    return null;
  }

  const settingsMenuItems = [
    {
      key: "platform",
      label: "Platform Settings",
      path: `/${sessionDetails?.orgName}/settings/platform`,
    },
    {
      key: "users",
      label: "User Management",
      path: `/${sessionDetails?.orgName}/users`,
    },
    {
      key: "triad",
      label: "Default Triad",
      path: `/${sessionDetails?.orgName}/settings/triad`,
    },
    {
      key: "review",
      label: "Human In the Loop Settings",
      path: `/${sessionDetails?.orgName}/settings/review`,
    },
  ];

  // Show sidebar when route changes (navigating to a new settings page)
  // location.key changes even when navigating to the same path
  useEffect(() => {
    setIsSidebarVisible(true);
  }, [location.pathname, location.key]);

  // Handle click outside to close sidebar
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (sidebarRef.current && !sidebarRef.current.contains(event.target)) {
        setIsSidebarVisible(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // Determine active key from route if not provided
  const getActiveKey = () => {
    if (activeKey) return activeKey;
    const path = location.pathname;
    if (path.includes("/settings/platform")) return "platform";
    if (path.includes("/users")) return "users";
    if (path.includes("/settings/triad")) return "triad";
    if (path.includes("/settings/review")) return "review";
    return "platform";
  };

  const currentActiveKey = getActiveKey();

  const handleKeyDown = (event, path) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      navigate(path);
    }
  };

  return (
    <div className="settings-container">
      {isSidebarVisible && (
        <nav className="settings-sidebar" ref={sidebarRef} aria-label="Settings navigation">
          {settingsMenuItems.map((item) => (
            <div
              key={item.key}
              className={`settings-menu-item ${
                currentActiveKey === item.key ? "active" : ""
              }`}
              onClick={() => navigate(item.path)}
              onKeyDown={(e) => handleKeyDown(e, item.path)}
              role="button"
              tabIndex={0}
              aria-label={item.label}
              aria-current={currentActiveKey === item.key ? "page" : undefined}
            >
              {item.label}
            </div>
          ))}
        </nav>
      )}
      <main className="settings-content" role="main">{children}</main>
    </div>
  );
}

SettingsLayout.propTypes = {
  children: PropTypes.node.isRequired,
  activeKey: PropTypes.string,
};

export { SettingsLayout };
