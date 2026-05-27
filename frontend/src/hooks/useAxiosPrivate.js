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
          // Skip logout on routes that intentionally render without a session.
          const onPublicShare =
            typeof globalThis !== "undefined" &&
            globalThis.location?.pathname.startsWith("/promptStudio/share/");
          if (onPublicShare) {
            // Keep a breadcrumb so a stray authenticated probe doesn't go silent.
            console.warn("[useAxiosPrivate] Suppressed 401 on public share", {
              url: error?.config?.url,
              path: globalThis.location?.pathname,
            });
          } else {
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
