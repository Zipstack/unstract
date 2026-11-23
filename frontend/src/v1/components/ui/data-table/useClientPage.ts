import { useState } from "react";

/*
 * The page a client-paged table shows. It goes back to page 1 when the sort
 * changes (the caller says so), when `filtered` flips, and when `resetKey`
 * changes (pass the search text). A page past the end (the rows shrank) is
 * clamped to the last page and stored; a render with no rows (a refetch)
 * leaves the page alone.
 */

export const DEFAULT_PAGE_SIZE = 25;

/** A usable page size: a whole number above 0, else the default. */
export function pageSizeOr(
  value: number | undefined,
  fallback = DEFAULT_PAGE_SIZE,
): number {
  return value !== undefined && Number.isFinite(value) && value >= 1
    ? Math.trunc(value)
    : fallback;
}

export type ClientPage = Readonly<{
  /** From 0, already clamped. */
  pageIndex: number;
  pageSize: number;
  setPageIndex: (index: number) => void;
  setPageSize: (size: number) => void;
}>;

export function useClientPage({
  rowCount,
  defaultPageSize,
  filtered,
  resetKey,
}: Readonly<{
  rowCount: number;
  defaultPageSize: number | undefined;
  filtered: boolean;
  resetKey: unknown;
}>): ClientPage {
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(() => pageSizeOr(defaultPageSize));
  const [seen, setSeen] = useState({ filtered, resetKey });

  let index = pageIndex;
  if (seen.filtered !== filtered || !Object.is(seen.resetKey, resetKey)) {
    // A new search or filter starts on page 1 (set during render, so the
    // stale page never shows).
    setSeen({ filtered, resetKey });
    index = 0;
  }
  const last = Math.max(0, Math.ceil(rowCount / pageSize) - 1);
  if (index > last && rowCount > 0) {
    index = last;
  }
  if (index !== pageIndex) {
    setPageIndex(index);
  }

  return {
    pageIndex: Math.min(index, last),
    pageSize,
    setPageIndex,
    setPageSize: (size) => setPageSize(pageSizeOr(size, pageSize)),
  };
}
