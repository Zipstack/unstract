import { hashKey, type QueryKey } from "@tanstack/react-query";

// The backend's paged-list contract (DRF PageNumberPagination): `?page=&page_size=`.

/** One page of a list endpoint. */
export type Page<T> = Readonly<{
  /** Rows across all pages. */
  count: number;
  next: string | null;
  previous: string | null;
  results: readonly T[];
}>;

/** Which page to fetch; `page` starts at 1. */
export type PageParams = Readonly<{ page: number; pageSize: number }>;

/** The query parameters for a page, as the backend names them. */
export function pageQuery({ page, pageSize }: PageParams) {
  return { page, page_size: pageSize } as const;
}

/* The key without its page number: the same organisation, list and filters. */
const listKey = (key: QueryKey): string =>
  hashKey(
    key.map((part) =>
      typeof part === "object" && part !== null && "page" in part
        ? { ...part, page: undefined }
        : part,
    ),
  );

/**
 * A paged query's `placeholderData`: the previous page stays on screen while
 * another page of the same list loads. Another organisation or filter shows
 * the loading state instead.
 */
export const previousPageOfList =
  <K extends QueryKey>(queryKey: K) =>
  <T>(
    previous: T | undefined,
    previousQuery?: { queryKey: K },
  ): T | undefined =>
    previousQuery && listKey(previousQuery.queryKey) === listKey(queryKey)
      ? previous
      : undefined;
