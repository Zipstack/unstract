import { useNavigate, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { useSessionStore } from "../../../store/session-store";

function Settings() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sessionDetails } = useSessionStore();

  useEffect(() => {
    // Redirect to platform settings if on base settings page
    if ((location.pathname.endsWith("/settings") || location.pathname.endsWith("/settings/")) && sessionDetails?.orgName) {
      navigate(`/${sessionDetails?.orgName}/settings/platform`, {
        replace: true,
      });
    }
  }, [location.pathname, navigate, sessionDetails?.orgName]);

  return null;
}

export { Settings };
