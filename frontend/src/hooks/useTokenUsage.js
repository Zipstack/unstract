import { useAlertStore } from "../store/alert-store";
import { useSessionStore } from "../store/session-store";
import { useAxiosPrivate } from "./useAxiosPrivate";
import { useExceptionHandler } from "./useExceptionHandler";

/**
 * Custom hook to fetch token usage data.
 *
 * @return {Object} - An object containing the getTokenUsage function.
 */
const useTokenUsage = () => {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const getTokenUsage = (runId, docId, setTokenUsage, defaultTokenUsage) => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/usage/get_token_usage/?run_id=${runId}`,
    };

    // Make the API request using the axios instance
    axiosPrivate(requestOptions)
      .then((res) => {
        const tokens = res?.data || defaultTokenUsage; // Use default token usage if response data is null or undefined
        // Update the token usage state with token usage data for a specific document ID
        setTokenUsage((prev) => ({
          ...prev,
          [docId]: tokens,
        }));
      })
      .catch((err) => {
        // Handle any errors that occur during the request
        setAlertDetails(handleException(err, "Failed to get token usage"));
      });
  };

  return { getTokenUsage };
};

export default useTokenUsage;
