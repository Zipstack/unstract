import type { QueryKey } from "@tanstack/react-query";

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

/**
 * A paged query's `placeholderData`: the previous page stays on screen while
 * the next loads, but never one from another organisation (keys start with it).
 */
export const previousPageInOrg =
  <K extends QueryKey>(queryKey: K) =>
  <T>(
    previous: T | undefined,
    previousQuery?: { queryKey: K },
  ): T | undefined =>
    previousQuery?.queryKey[0] === queryKey[0] ? previous : undefined;
