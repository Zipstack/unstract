import axios from "axios";
import { useEffect, useMemo } from "react";

import useLogout from "./useLogout";

function useAxiosPrivate() {
  const logout = useLogout();
  const axiosPrivate = useMemo(() => axios.create(), []);

  useEffect(() => {
    const responseInterceptor = axiosPrivate.interceptors.response.use(
      (response) => {
        return response;
      },
      async (error) => {
        if (error?.response?.status === 401) {
          // Anonymous share viewer has no session to log out of; a 401
          // here is a misrouted authenticated probe, not an expired session.
          const onPublicShare =
            typeof window !== "undefined" &&
            window.location.pathname.startsWith("/promptStudio/share");
          if (!onPublicShare) {
            // TODO: Implement Session Expired Modal
            logout();
          }
        }
        return Promise.reject(error);
      },
    );

    return () => {
      axiosPrivate.interceptors.response.eject(responseInterceptor);
    };
  }, []);
  return axiosPrivate;
}

export { useAxiosPrivate };
