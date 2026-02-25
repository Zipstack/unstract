import { useState, useRef, useEffect } from "react";

/**
 * Shared hook for scroll restoration when navigating back to a list page.
 * Restores pagination, search, and scroll position from location.state.
 *
 * @param {Object} options
 * @param {Object} options.location - react-router location object
 * @param {Function} options.setSearchTerm - from usePaginatedList
 * @param {Function} options.setPagination - from usePaginatedList
 * @param {Function} options.fetchData - fn(page, pageSize, search) to fetch data
 * @return {Object} Scroll restoration state and helpers
 */
function useScrollRestoration({
  location,
  setSearchTerm,
  setPagination,
  fetchData,
}) {
  const [scrollRestoreId, setScrollRestoreId] = useState(null);
  const pendingScrollIdRef = useRef(null);

  const fetchRef = useRef(fetchData);
  fetchRef.current = fetchData;

  useEffect(() => {
    if (location.state?.scrollToCardId) {
      pendingScrollIdRef.current = location.state.scrollToCardId;

      const { page, pageSize, searchTerm: savedSearch } = location.state;
      const restoredPage = page || 1;
      const restoredPageSize = pageSize || 10;
      const restoredSearch = savedSearch || "";
      setSearchTerm(restoredSearch);
      setPagination((prev) => ({
        ...prev,
        current: restoredPage,
        pageSize: restoredPageSize,
      }));
      fetchRef.current?.(restoredPage, restoredPageSize, restoredSearch);
    }
  }, [location.key]);

  const activateScrollRestore = () => {
    if (pendingScrollIdRef.current) {
      setScrollRestoreId(pendingScrollIdRef.current);
      pendingScrollIdRef.current = null;
      setTimeout(() => setScrollRestoreId(null), 500);
    }
  };

  const clearPendingScroll = () => {
    pendingScrollIdRef.current = null;
  };

  return { scrollRestoreId, activateScrollRestore, clearPendingScroll };
}

export { useScrollRestoration };
