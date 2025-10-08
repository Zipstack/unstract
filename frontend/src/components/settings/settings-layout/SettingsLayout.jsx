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
      label: "Human In the Loop  Settings",
      path: `/${sessionDetails?.orgName}/settings/review`,
    },
  ];

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
    if (path.includes("platform")) return "platform";
    if (path.includes("users")) return "users";
    if (path.includes("triad")) return "triad";
    if (path.includes("review")) return "review";
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
        <div className="settings-sidebar" ref={sidebarRef}>
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
            >
              {item.label}
            </div>
          ))}
        </div>
      )}
      <div className="settings-content">{children}</div>
    </div>
  );
}

SettingsLayout.propTypes = {
  children: PropTypes.node.isRequired,
  activeKey: PropTypes.string,
};

export { SettingsLayout };
