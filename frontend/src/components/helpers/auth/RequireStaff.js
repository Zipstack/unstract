import { Outlet } from "react-router-dom";

import { useSessionStore } from "../../../store/session-store";
import { Unauthorized } from "../../error/UnAuthorized/Unauthorized.jsx";
import { NotFound } from "../../error/NotFound/NotFound.jsx";

const RequireStaff = () => {
  const { sessionDetails } = useSessionStore();
  const isStaff = sessionDetails?.isStaff || sessionDetails?.is_staff;
  const orgName = sessionDetails?.orgName;
  const isOpenSource = orgName === "mock_org";

  if (!isStaff) {
    return <Unauthorized />;
  }
  if (isOpenSource) {
    return <NotFound />;
  }

  return <Outlet />;
};

export { RequireStaff };
