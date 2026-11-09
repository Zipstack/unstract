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

  return () => {
    setLogoutLoading(true);
    setSessionDetails(getSessionData(null));
    posthog.reset();
    clearSessionCookies();
    // A page navigation, not a request: the backend redirects to the identity
    // provider's logout, which answers no CORS request from this origin, and
    // the provider sends the browser on to /landing.
    window.location.href = `${getBaseUrl()}/api/v1/logout`;
  };
}

export default useLogout;
