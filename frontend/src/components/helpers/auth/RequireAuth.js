import { Navigate, Outlet, useLocation } from "react-router-dom";

import { getOrgNameFromPathname } from "../../../helpers/GetStaticData";
import { useSessionStore } from "../../../store/session-store";

const RequireAuth = () => {
  const { sessionDetails } = useSessionStore();
  const location = useLocation();
  const isLoggedIn = sessionDetails?.isLoggedIn;
  const orgName = sessionDetails?.orgName;
  const pathname = location?.pathname;
  const currOrgName = getOrgNameFromPathname(pathname);

  if (!isLoggedIn) {
    return <Navigate to="/landing" state={{ from: location }} replace />;
  }

  if (currOrgName !== orgName) {
    return <Navigate to={`/${orgName}/onboard`} />;
  }

  return <Outlet />;
};

export { RequireAuth };
