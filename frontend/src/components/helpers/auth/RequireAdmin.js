import { Outlet } from "react-router-dom";

import { useSessionStore } from "../../../store/session-store";
import { Unauthorized } from "../../error/UnAuthorized/Unauthorized.jsx";
import { NotFound } from "../../error/NotFound/NotFound.jsx";

const RequireAdmin = () => {
  const { sessionDetails } = useSessionStore();
  const isAdmin = sessionDetails?.isAdmin;
  const orgName = sessionDetails?.orgName;
  const isOpenSource = orgName === "mock_org";

  if (!isAdmin) {
    return <Unauthorized />;
  }
  if (isOpenSource) {
    return <NotFound />;
  }

  return <Outlet />;
};

export { RequireAdmin };
