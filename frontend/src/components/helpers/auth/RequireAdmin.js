import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
import { NotFound } from "../../error/NotFound/NotFound.jsx";
import { Unauthorized } from "../../error/UnAuthorized/Unauthorized.jsx";

const RequireAdmin = () => {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails, updateSessionDetails } = useSessionStore();
  const [isVerifying, setIsVerifying] = useState(true);
  const orgId = sessionDetails?.orgId;
  const orgName = sessionDetails?.orgName;
  const isOpenSource = orgName === "mock_org";

  useEffect(() => {
    const verifyAdminStatus = async () => {
      try {
        const res = await axiosPrivate.get(
          `/api/v1/unstract/${orgId}/users/profile/`,
          { headers: { "X-CSRFToken": sessionDetails?.csrfToken } },
        );
        const currentIsAdmin = res?.data?.user?.is_admin;
        const currentRole = res?.data?.user?.role;
        const updates = {};
        if (currentIsAdmin !== sessionDetails?.isAdmin) {
          updates.isAdmin = currentIsAdmin;
        }
        if (currentRole && currentRole !== sessionDetails?.role) {
          updates.role = currentRole;
        }
        if (Object.keys(updates).length > 0) {
          updateSessionDetails(updates);
        }
      } catch {
        // On error, keep current session state
      } finally {
        setIsVerifying(false);
      }
    };

    if (orgId) {
      verifyAdminStatus();
    } else {
      setIsVerifying(false);
    }
  }, [orgId]);

  if (isVerifying) {
    return null;
  }

  if (!sessionDetails?.isAdmin) {
    return <Unauthorized />;
  }
  if (isOpenSource) {
    return <NotFound />;
  }
  return <Outlet />;
};

export { RequireAdmin };
