import Cookies from "js-cookie";
import { usePostHog } from "posthog-js/react";
import { getSessionData } from "../helpers/GetSessionData";
import { getBaseUrl } from "../helpers/GetStaticData";
import { useSessionStore } from "../store/session-store";

function useLogout() {
  const setSessionDetails = useSessionStore((state) => state.setSessionDetails);
  const posthog = usePostHog();

  const clearSessionCookies = () => {
    Cookies.remove("sessionid");
    Cookies.remove("csrftoken");
  };

  return () => {
    setSessionDetails(getSessionData(null));
    localStorage.removeItem("selectedProduct");
    posthog.reset();
    clearSessionCookies();
    const baseUrl = getBaseUrl();
    const newURL = baseUrl + "/api/v1/logout";
    window.location.href = newURL;
  };
}

export default useLogout;
