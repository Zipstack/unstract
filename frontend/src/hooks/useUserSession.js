import axios from "axios";
import { useNavigate } from "react-router-dom";

import { useExceptionHandler } from "../hooks/useExceptionHandler.jsx";
import { useAlertStore } from "../store/alert-store";
const useUserSession = () => {
  const navigate = useNavigate();
  const handleException = useExceptionHandler();
  const { setAlertDetails } = useAlertStore();
  const fallbackErrorMessage = "Error while getting session";

  return async () => {
    try {
      const requestOptions = {
        method: "GET",
        url: "/api/v1/session",
      };
      const res = await axios(requestOptions);
      return res.data;
    } catch (error) {
      if (error?.response?.statusText === "Unauthorized") {
        return;
      }

      if (error?.response?.statusText === "Payment Required") {
        navigate("/trial-expired");
        return;
      }

      setAlertDetails(handleException(error, fallbackErrorMessage));
    }
  };
};
export { useUserSession };
