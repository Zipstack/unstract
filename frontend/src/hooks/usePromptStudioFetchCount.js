import { useEffect, useState, useCallback, useRef } from "react";

/**
 * Custom hook to fetch count and track initial fetch completion.
 * @param {Function} fetchCount - The fetchCount function from your store.
 * @param {Function} getPromptStudioCount - The function to get the count.
 * @return {boolean} initialFetchComplete
 */
export function useInitialFetchCount(fetchCount, getPromptStudioCount) {
  const [initialFetchComplete, setInitialFetchComplete] = useState(false);
  const hasFetchedRef = useRef(false);

  useEffect(() => {
    // Only fetch once and prevent re-fetching
    if (!hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchCount(getPromptStudioCount).finally(() => {
        setInitialFetchComplete(true);
      });
    }
  }, [fetchCount, getPromptStudioCount]);

  return initialFetchComplete;
}

/**
 * Custom hook to manage prompt studio modal visibility based on item count
 * @param {boolean} initialFetchComplete - Whether the initial data fetch is complete
 * @param {boolean} isLoading - Whether data is currently loading
 * @param {number} count - The count of items (workflows, deployments, etc.)
 * @return {Object} - Modal state and handlers
 */
export function usePromptStudioModal(initialFetchComplete, isLoading, count) {
  const [showModal, setShowModal] = useState(false);
  const [modalDismissed, setModalDismissed] = useState(false);

  useEffect(() => {
    if (initialFetchComplete && !isLoading && count === 0 && !modalDismissed) {
      setShowModal(true);
    } else if (!isLoading && count > 0) {
      setShowModal(false);
    }
  }, [initialFetchComplete, isLoading, count, modalDismissed]);

  const handleModalClose = useCallback(() => {
    setShowModal(false);
    setModalDismissed(true); // Prevent modal reopen
  }, []);

  return {
    showModal,
    handleModalClose,
  };
}
