import { useRef, useState } from "react";

/**
 * Shared hook for paginated list state and handlers.
 * Uses a ref internally to avoid stale closure issues with fetchData.
 *
 * @param {Object} options
 * @param {Function} options.fetchData - fn(page, pageSize, search, sortBy, order)
 * @param {number} [options.defaultPageSize=10]
 * @param {string} [options.defaultSortBy=""] - initial sort column key
 * @param {string} [options.defaultOrder="asc"] - initial sort direction
 * @return {Object} Pagination/sort state and handlers
 */
function usePaginatedList({
  fetchData,
  defaultPageSize = 10,
  defaultSortBy = "",
  defaultOrder = "asc",
}) {
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: defaultPageSize,
    total: 0,
  });
  const [searchTerm, setSearchTerm] = useState("");
  const [sort, setSort] = useState({
    sortBy: defaultSortBy,
    order: defaultOrder,
  });

  const fetchRef = useRef(fetchData);
  fetchRef.current = fetchData;

  const handlePaginationChange = (page, pageSize) => {
    const newPage = pageSize === pagination.pageSize ? page : 1;
    fetchRef.current?.(newPage, pageSize, searchTerm, sort.sortBy, sort.order);
  };

  const handleSearch = (searchText) => {
    const term = searchText?.trim() || "";
    setSearchTerm(term);
    fetchRef.current?.(1, pagination.pageSize, term, sort.sortBy, sort.order);
  };

  // Table header sort click: reset to page 1 (the page a row sits on changes)
  // and refetch with the new ordering.
  const handleSortChange = (sortBy, order) => {
    const nextSort = { sortBy: sortBy || "", order: order || "asc" };
    setSort(nextSort);
    fetchRef.current?.(
      1,
      pagination.pageSize,
      searchTerm,
      nextSort.sortBy,
      nextSort.order,
    );
  };

  return {
    pagination,
    setPagination,
    searchTerm,
    setSearchTerm,
    sort,
    handlePaginationChange,
    handleSearch,
    handleSortChange,
  };
}

export { usePaginatedList };
