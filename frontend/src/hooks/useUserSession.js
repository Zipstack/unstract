import { clearUserLocalStorage } from "@v1";
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
      const timestamp = new Date().getTime();
      const requestOptions = {
        method: "GET",
        url: `/api/v1/session?q=${timestamp}`,
      };
      const res = await axios(requestOptions);
      return res.data;
    } catch (error) {
      if (error?.response?.data?.message === "Unauthorized") {
        // No session, e.g. it expired without a logout: drop what the last
        // user left in localStorage. sessionStorage is per tab and holds the
        // silent sign-in loop guard, so it is left alone here.
        clearUserLocalStorage();
        return;
      }

      if (error?.response?.data?.type === "subscription_error") {
        navigate("/subscription-expired");
        return;
      }

      setAlertDetails(handleException(error, fallbackErrorMessage));
    }
  };
};

export { useUserSession };
