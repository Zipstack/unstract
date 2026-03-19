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
          // TODO: Implement Session Expired Modal
          logout();
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
