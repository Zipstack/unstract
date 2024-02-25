import { Navigate, Outlet, useLocation } from "react-router-dom";

import { publicRoutes } from "../../../helpers/GetStaticData";
import { useSessionStore } from "../../../store/session-store";

const RequireGuest = () => {
  const { sessionDetails } = useSessionStore();
  const location = useLocation();
  const pathname = location.pathname;

  return !sessionDetails?.isLoggedIn && publicRoutes.includes(pathname) ? (
    <Outlet />
  ) : (
    <Navigate to={`/${sessionDetails?.orgName}/onboard`} />
  );
};

export { RequireGuest };
