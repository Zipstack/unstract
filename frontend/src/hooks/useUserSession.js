import axios from "axios";

import { useExceptionHandler } from "../hooks/useExceptionHandler.jsx";
import { useAlertStore } from "../store/alert-store";
const useUserSession = () => {
  const handleException = useExceptionHandler();
  const { setAlertDetails } = useAlertStore();
  return async () => {
    try {
      const requestOptions = {
        method: "GET",
        url: "/api/v1/session",
      };
      const res = await axios(requestOptions);
      return res.data;
    } catch (error) {
      if (error?.response?.statusText === "Payment Required") {
        handleException(error, "Error while getting session");
      } else if (error?.response?.statusText === "Unauthorized") {
        handleException(error, "Error while getting session");
      } else {
        setAlertDetails(handleException(error, "Error while getting session"));
      }
    }
  };
};
export { useUserSession };
