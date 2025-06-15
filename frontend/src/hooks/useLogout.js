import axios from "axios";
import Cookies from "js-cookie";
import { usePostHog } from "posthog-js/react";

import { getSessionData } from "../helpers/GetSessionData";
import { getBaseUrl } from "../helpers/GetStaticData";
import { useSessionStore } from "../store/session-store";

function useLogout() {
  const setSessionDetails = useSessionStore((state) => state.setSessionDetails);
  const setLogoutLoading = useSessionStore((state) => state.setLogoutLoading);
  const posthog = usePostHog();

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
      // ignore errors and proceed to navigation
    }
    setLogoutLoading(false);
    window.location.href = baseUrl + "/";
  };
}

export default useLogout;
