import { useEffect, useState } from "react";

/**
 * Custom hook to fetch count and track initial fetch completion.
 * @param {Function} fetchCount - The fetchCount function from your store.
 * @param {Function} getPromptStudioCount - The function to get the count.
 * @returns {boolean} initialFetchComplete
 */
export function useInitialFetchCount(fetchCount, getPromptStudioCount) {
  const [initialFetchComplete, setInitialFetchComplete] = useState(false);

  useEffect(() => {
    fetchCount(getPromptStudioCount).finally(() => {
      setInitialFetchComplete(true);
    });
  }, [fetchCount, getPromptStudioCount]);

  return initialFetchComplete;
}
