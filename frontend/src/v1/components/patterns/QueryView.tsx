import type { UseQueryResult } from "@tanstack/react-query";
import { InlineCode } from "@v1/components/ui/code";
import { InlineAlert, SkeletonText } from "@v1/components/ui/feedback";
import { toApiError } from "@v1/services/errors";
import type { JSX, ReactNode } from "react";

export type QueryViewProps<T> = Readonly<{
  query: UseQueryResult<T>;
  /** Shown while loading; default three skeleton lines. */
  loading?: ReactNode;
  children: (data: T) => ReactNode;
}>;

/**
 * Renders a query's three states: a skeleton while loading, an InlineAlert
 * with Retry when the first fetch failed, and `children(data)` otherwise
 * (a failed refresh keeps the data; app/query.ts toasts it).
 */
export function QueryView<T>({
  query,
  loading,
  children,
}: QueryViewProps<T>): JSX.Element {
  const skeleton = <>{loading ?? <SkeletonText />}</>;
  if (query.status === "pending") {
    return skeleton;
  }
  // The first fetch failed: decided on the cache, as app/query.ts does, not on `select`'s result.
  if (query.isError && query.dataUpdatedAt === 0) {
    // An expired session has already sent the page to sign in.
    return isExpired(query.error) ? (
      skeleton
    ) : (
      <FirstFetchError query={query} />
    );
  }
  // A select that throws during a fetch has no data; the boundary gets it once the fetch settles.
  if (query.isError && query.isFetching && query.data === undefined) {
    return skeleton;
  }
  return <>{children(query.data as T)}</>;
}

const isExpired = (error: unknown): boolean =>
  toApiError(error).kind === "unauthenticated";

/* Retry puts the query back to loading, so the alert gives way to the skeleton at once. */
function FirstFetchError({
  query,
}: Readonly<{ query: UseQueryResult<unknown> }>): JSX.Element {
  const error = toApiError(query.error);
  return (
    <InlineAlert title={error.message} onRetry={() => void query.refetch()}>
      {error.requestId ? (
        <>
          Request ID <InlineCode variant="plain">{error.requestId}</InlineCode>
        </>
      ) : null}
    </InlineAlert>
  );
}
