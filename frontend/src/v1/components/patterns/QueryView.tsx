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
  if (query.status === "pending") {
    return <>{loading ?? <SkeletonText />}</>;
  }
  // The first fetch failed: decided on the cache, as app/query.ts does, not on `select`'s result.
  if (query.isError && query.dataUpdatedAt === 0) {
    const error = toApiError(query.error);
    return (
      <InlineAlert title={error.message} onRetry={() => void query.refetch()}>
        {error.requestId ? (
          <>
            Request ID{" "}
            <InlineCode variant="plain">{error.requestId}</InlineCode>
          </>
        ) : null}
      </InlineAlert>
    );
  }
  return <>{children(query.data as T)}</>;
}
