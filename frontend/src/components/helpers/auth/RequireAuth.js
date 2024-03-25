import { Navigate, Outlet, useLocation } from "react-router-dom";

import {
  getOrgNameFromPathname,
  onboardCompleted,
} from "../../../helpers/GetStaticData";
import { useSessionStore } from "../../../store/session-store";

const RequireAuth = () => {
  const { sessionDetails } = useSessionStore();
  const location = useLocation();
  const isLoggedIn = sessionDetails?.isLoggedIn;
  const orgName = sessionDetails?.orgName;
  const pathname = location?.pathname;
  const adapters = sessionDetails?.adapters;
  const currOrgName = getOrgNameFromPathname(pathname);

  let navigateTo = `/${orgName}/onboard`;
  if (onboardCompleted(adapters)) {
    navigateTo = `/${orgName}/tools`;
  }

  if (!isLoggedIn) {
    return <Navigate to="/landing" state={{ from: location }} replace />;
  }

  if (currOrgName !== orgName) {
    return <Navigate to={navigateTo} />;
  }

  return <Outlet />;
};

export { RequireAuth };
