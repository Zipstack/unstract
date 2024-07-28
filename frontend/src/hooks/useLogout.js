import { usePostHog } from "posthog-js/react";
import { getSessionData } from "../helpers/GetSessionData";
import { getBaseUrl } from "../helpers/GetStaticData";
import { useSessionStore } from "../store/session-store";

function useLogout() {
  const setSessionDetails = useSessionStore((state) => state.setSessionDetails);
  const posthog = usePostHog();

  return () => {
    setSessionDetails(getSessionData(null));
    localStorage.removeItem("selectedProduct");
    posthog.reset();
    const baseUrl = getBaseUrl();
    const newURL = baseUrl + "/api/v1/logout";
    window.location.href = newURL;
  };
}

export default useLogout;
