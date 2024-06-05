import { useAlertStore } from "../store/alert-store";
import { useSessionStore } from "../store/session-store";
import { useTokenUsageStore } from "../store/token-usage-store";
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
  const { setTokenUsage } = useTokenUsageStore();

  const getTokenUsage = (runId, tokenUsageId) => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/usage/get_token_usage/?run_id=${runId}`,
    };

    // Make the API request using the axios instance
    axiosPrivate(requestOptions)
      .then((res) => {
        const tokens = res?.data;
        // Update the token usage state with token usage data for a specific tokenUsageId
        setTokenUsage(tokenUsageId, tokens);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to get token usage"));
      });
  };

  return { getTokenUsage };
};

export default useTokenUsage;
