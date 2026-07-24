import { useCallback, useEffect, useRef, useState } from "react";

import { unwrapList } from "../helpers/pagination";

const DEFAULT_PAGE_SIZE = 10;

/**
 * Server-side paginated list state for the shared resource endpoints.
 *
 * Owns the request so every list page behaves the same way: page/page_size/
 * search params, response unwrapping, the empty-page step back, in-flight
 * response ordering, and the loading flag.
 *
 * @param {Object} options
 * @param {Function} options.request - fn(params) resolving to the axios response
 * @param {Function} [options.onError] - called with the request error
 * @param {number} [options.defaultPageSize=10]
 * @return {Object} List state and handlers
 */
function usePaginatedResource({
  request,
  onError,
  defaultPageSize = DEFAULT_PAGE_SIZE,
}) {
  const [items, setItems] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: defaultPageSize,
    total: 0,
  });
  const [searchTerm, setSearchTerm] = useState("");

  // Effect, not a render-time write: mutating a ref during render is unsafe
  // under concurrent rendering, where a render can be discarded.
  const requestRef = useRef(request);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    requestRef.current = request;
    onErrorRef.current = onError;
  });

  // Only the newest request may write state. A slower earlier one would
  // otherwise resurrect the previous page, search term or resource type.
  const latestRequestId = useRef(0);

  const fetchPage = useCallback(
    async (page = 1, pageSize = defaultPageSize, search = "") => {
      const requestId = ++latestRequestId.current;
      const isCurrent = () => requestId === latestRequestId.current;

      setIsLoading(true);
      try {
        const params = { page, page_size: pageSize };
        if (search) {
          params.search = search;
        }
        const res = await requestRef.current?.(params);
        if (!isCurrent()) {
          return;
        }
        const results = unwrapList(res);
        const total = res?.data?.count ?? results.length;
        // Deleting the last row on a page leaves it empty; step back a page.
        // Awaited so the loading flag outlives the replacement request.
        if (!results.length && page > 1 && total > 0) {
          return await fetchPage(page - 1, pageSize, search);
        }
        setItems(results);
        setPagination((prev) => ({ ...prev, current: page, pageSize, total }));
      } catch (err) {
        if (isCurrent()) {
          onErrorRef.current?.(err);
        }
      } finally {
        // A superseding request owns the flag once it has started.
        if (isCurrent()) {
          setIsLoading(false);
        }
      }
    },
    [defaultPageSize],
  );

  const handlePaginationChange = useCallback(
    (page, pageSize) => {
      // A changed page size invalidates the offset, so restart at page 1.
      const nextPage = pageSize === pagination.pageSize ? page : 1;
      fetchPage(nextPage, pageSize, searchTerm);
    },
    [fetchPage, pagination.pageSize, searchTerm],
  );

  const handleSearch = useCallback(
    (searchText) => {
      const term = searchText?.trim() || "";
      setSearchTerm(term);
      fetchPage(1, pagination.pageSize, term);
    },
    [fetchPage, pagination.pageSize],
  );

  // Re-runs the current page, preserving the page and any active search.
  const refresh = useCallback(
    () => fetchPage(pagination.current, pagination.pageSize, searchTerm),
    [fetchPage, pagination.current, pagination.pageSize, searchTerm],
  );

  return {
    items,
    setItems,
    isLoading,
    setIsLoading,
    pagination,
    setPagination,
    searchTerm,
    setSearchTerm,
    fetchPage,
    refresh,
    handlePaginationChange,
    handleSearch,
  };
}

export { usePaginatedResource };
