import axios from "axios";
import { useEffect, useMemo } from "react";

import { attachRequestIdInterceptor } from "../helpers/requestId";
import useLogout from "./useLogout";

function useAxiosPrivate() {
  const logout = useLogout();
  const axiosPrivate = useMemo(() => axios.create(), []);

  useEffect(() => {
    const requestInterceptor = attachRequestIdInterceptor(axiosPrivate);
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
      axiosPrivate.interceptors.request.eject(requestInterceptor);
      axiosPrivate.interceptors.response.eject(responseInterceptor);
    };
  }, []);
  return axiosPrivate;
}

export { useAxiosPrivate };
