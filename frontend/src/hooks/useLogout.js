import axios from "axios";
import Cookies from "js-cookie";
import { usePostHog } from "posthog-js/react";

import { getSessionData } from "../helpers/GetSessionData";
import { getBaseUrl } from "../helpers/GetStaticData";
import { useSessionStore } from "../store/session-store";
import { useAlertStore } from "../store/alert-store";
import { useExceptionHandler } from "./useExceptionHandler";

function useLogout() {
  const setSessionDetails = useSessionStore((state) => state.setSessionDetails);
  const setLogoutLoading = useSessionStore((state) => state.setLogoutLoading);
  const posthog = usePostHog();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const clearSessionCookies = () => {
    Cookies.remove("sessionid");
    Cookies.remove("csrftoken");
  };

  return async () => {
    setLogoutLoading(true);
    setSessionDetails(getSessionData(null));
    posthog.reset();
    clearSessionCookies();
    const baseUrl = getBaseUrl();
    try {
      await axios.get(baseUrl + "/api/v1/logout");
    } catch (error) {
      setAlertDetails(handleException(error));
    }
    setLogoutLoading(false);
    window.location.href = baseUrl + "/";
  };
}

export default useLogout;
