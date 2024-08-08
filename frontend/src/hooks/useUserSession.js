import axios from "axios";
import { useNavigate, useLocation } from "react-router-dom";

import { useExceptionHandler } from "../hooks/useExceptionHandler.jsx";
import { useAlertStore } from "../store/alert-store";

const useUserSession = () => {
  const navigate = useNavigate();
  const handleException = useExceptionHandler();
  const { setAlertDetails } = useAlertStore();
  const fallbackErrorMessage = "Error while getting session";

  const location = useLocation();

  return async () => {
    try {
      const requestOptions = {
        method: "GET",
        url: "/api/v1/session",
      };
      const res = await axios(requestOptions);
      return res.data;
    } catch (error) {
      if (error?.response?.data?.message === "Unauthorized") {
        return;
      }

      if (error?.response?.data?.type === "subscription_error") {
        if (location?.pathname === "/plans") {
          return;
        }

        navigate("/trial-expired");
        return;
      }

      setAlertDetails(handleException(error, fallbackErrorMessage));
    }
  };
};
export { useUserSession };
