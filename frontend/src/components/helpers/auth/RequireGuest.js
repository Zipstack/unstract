import { Navigate, Outlet, useLocation } from "react-router-dom";

import { publicRoutes, onboardCompleted } from "../../../helpers/GetStaticData";
import { useSessionStore } from "../../../store/session-store";

const RequireGuest = () => {
  const { sessionDetails } = useSessionStore();
  const { orgName, adapters } = sessionDetails;
  const location = useLocation();
  const pathname = location.pathname;
  let navigateTo = `/${orgName}/onboard`;
  if (onboardCompleted(adapters)) {
    navigateTo = `/${orgName}/etl`;
  }

  return !sessionDetails?.isLoggedIn && publicRoutes.includes(pathname) ? (
    <Outlet />
  ) : (
    <Navigate to={navigateTo} />
  );
};

export { RequireGuest };
