import { useSessionStore } from "../store/session-store";

const useRequestUrl = () => {
  const { sessionDetails } = useSessionStore();

  const getUrl = (url) => {
    if (!url) return null;

    const baseUrl = `/api/v1/unstract/${sessionDetails?.orgId}/`;
    return baseUrl + url.replace(/^\//, "");
  };

  return { getUrl };
};

export default useRequestUrl;
