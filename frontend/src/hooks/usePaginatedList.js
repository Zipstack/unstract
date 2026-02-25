import { useState, useRef } from "react";

/**
 * Shared hook for paginated list state and handlers.
 * Uses a ref internally to avoid stale closure issues with fetchData.
 *
 * @param {Object} options
 * @param {Function} options.fetchData - fn(page, pageSize, search) to fetch data
 * @param {number} [options.defaultPageSize=10]
 * @return {Object} Pagination state and handlers
 */
function usePaginatedList({ fetchData, defaultPageSize = 10 }) {
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: defaultPageSize,
    total: 0,
  });
  const [searchTerm, setSearchTerm] = useState("");

  const fetchRef = useRef(fetchData);
  fetchRef.current = fetchData;

  const handlePaginationChange = (page, pageSize) => {
    const newPage = pageSize === pagination.pageSize ? page : 1;
    fetchRef.current?.(newPage, pageSize, searchTerm);
  };

  const handleSearch = (searchText) => {
    const term = searchText?.trim() || "";
    setSearchTerm(term);
    fetchRef.current?.(1, pagination.pageSize, term);
  };

  return {
    pagination,
    setPagination,
    searchTerm,
    setSearchTerm,
    handlePaginationChange,
    handleSearch,
  };
}

export { usePaginatedList };
