import { useCallback, useRef, useState } from "react";

/**
 * Build the query params for a paginated list request, omitting empty
 * search/sort so non-paginated callers stay unaffected. Callers add any
 * resource-specific params (e.g. `adapter_type`) to the returned object.
 *
 * @param {Object} args
 * @param {number} args.page - Requested page.
 * @param {number} args.pageSize - Requested page size.
 * @param {string} [args.search] - Search term.
 * @param {string} [args.sortBy] - Sort column key.
 * @param {string} [args.order] - Sort direction.
 * @return {Object} Query params.
 */
function buildPagedParams({ page, pageSize, search, sortBy, order }) {
  const params = { page, page_size: pageSize };
  if (search) {
    params.search = search;
  }
  if (sortBy) {
    params.sort_by = sortBy;
    params.order = order;
  }
  return params;
}

/**
 * Commit a paginated list response, shared by every resource list page.
 *
 * Unwraps the opt-in envelope (`{results, count}` or a bare array), drops stale
 * responses that a newer request already superseded, and steps back a page when
 * a delete empties the last one — returning that refetch promise so the caller's
 * `finally` waits for replacement data instead of clearing loading early.
 *
 * @param {Object} args
 * @param {*} args.data - `res.data`: envelope or bare array.
 * @param {number} args.page - Requested page.
 * @param {number} args.pageSize - Requested page size.
 * @param {number} args.seq - This request's sequence token.
 * @param {{current: number}} args.latestSeqRef - Ref holding the newest token.
 * @param {Function} args.setList - List state setter.
 * @param {Function} args.setPagination - Pagination state setter.
 * @param {Function} args.refetchPrevPage - Refetches `page - 1`; its promise is
 *   returned so the caller's `finally` waits for it.
 * @return {Promise|undefined}
 */
function applyPagedResponse({
  data,
  page,
  pageSize,
  seq,
  latestSeqRef,
  setList,
  setPagination,
  refetchPrevPage,
}) {
  // A newer request already fired — ignore this superseded response.
  if (seq !== latestSeqRef.current) {
    return undefined;
  }
  const results = data?.results ?? data ?? [];
  const total = data?.count ?? results.length;
  // Deleting the last row on a page leaves it empty; step back a page.
  if (results.length === 0 && page > 1 && total > 0) {
    return refetchPrevPage();
  }
  setList(results);
  setPagination((prev) => ({ ...prev, current: page, pageSize, total }));
  return undefined;
}

/**
 * Shared hook for paginated list state and handlers.
 *
 * Owns `fetchRef` — the page assigns its fetch fn to `fetchRef.current`, and the
 * hook's handlers (search/sort/paginate) plus `handleListRefresh` invoke the
 * latest one, so pages don't re-derive that wiring. `handleListRefresh` refetches
 * the current page preserving active search/sort — pass it to mutation callbacks.
 *
 * @param {Object} [options]
 * @param {number} [options.defaultPageSize=10]
 * @param {string} [options.defaultSortBy=""] - initial sort column key
 * @param {string} [options.defaultOrder="asc"] - initial sort direction
 * @return {Object} Pagination/sort state, `fetchRef`, and handlers.
 */
function usePaginatedList({
  defaultPageSize = 10,
  defaultSortBy = "",
  defaultOrder = "asc",
} = {}) {
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

  // Page assigns its fetch fn here; handlers call the latest one via the ref.
  const fetchRef = useRef(null);

  // Mirror the latest list params so handleListRefresh always refetches the
  // CURRENT view, even when captured earlier (e.g. a pending mutation's .then)
  // before the user changed page/search/sort.
  const listStateRef = useRef();
  listStateRef.current = { pagination, searchTerm, sort };

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

  // Stable identity, reads the latest params from the ref: a refresh captured
  // before the user navigated still fetches the view they're on now instead of
  // restoring the stale page/search/order.
  const handleListRefresh = useCallback(() => {
    const { pagination: p, searchTerm: term, sort: s } = listStateRef.current;
    fetchRef.current?.(p.current, p.pageSize, term, s.sortBy, s.order);
  }, []);

  return {
    pagination,
    setPagination,
    searchTerm,
    setSearchTerm,
    sort,
    fetchRef,
    handlePaginationChange,
    handleSearch,
    handleSortChange,
    handleListRefresh,
  };
}

export { applyPagedResponse, buildPagedParams, usePaginatedList };
