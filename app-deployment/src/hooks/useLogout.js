import { getSessionData } from "../helpers/GetSessionData";
import { getBaseUrl } from "../helpers/GetStaticData";
import { useSessionStore } from "../store/session-store";

function useLogout() {
  const setSessionDetails = useSessionStore((state) => state.setSessionDetails);

  return () => {
    setSessionDetails(getSessionData(null));
    const baseUrl = getBaseUrl();
    const newURL = baseUrl + "/api/v1/logout";
    window.location.href = newURL;
  };
}

export default useLogout;
