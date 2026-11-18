import {
  type DefaultOptions,
  type Mutation,
  MutationCache,
  type Query,
  QueryCache,
  QueryClient,
} from "@tanstack/react-query";
import { isTransient, toApiError } from "@v1/services/errors";
import { reportApiError } from "@v1/services/report";

// Server state for v1; every failure is reported once, here (services/README.md).

const MAX_READ_RETRIES = 2;
// One toast for every query that cannot reach the server, not one each.
const NETWORK_TOAST_ID = "v1-network";

/** Reads retry only on transient failures; mutations never retry. */
export function retryRead(failureCount: number, error: unknown): boolean {
  return failureCount < MAX_READ_RETRIES && isTransient(error);
}

function reportQueryError(
  error: Error,
  query: Query<unknown, unknown, unknown>,
): void {
  // A failed refresh keeps stale data on screen, so only then a toast.
  const notify = query.state.data !== undefined;
  const network = toApiError(error).kind === "network";
  reportApiError(error, {
    notify,
    id: network ? NETWORK_TOAST_ID : query.queryHash,
  });
}

// Only a `select` that threw (not the cached query's own error): a bug, for the error boundary.
const throwSelectError = (error: Error, query: Query) =>
  error !== query.state.error;

function reportMutationError(
  error: Error,
  _variables: unknown,
  _onMutateResult: unknown,
  mutation: Mutation<unknown, unknown, unknown>,
): void {
  reportApiError(error, { notify: mutation.meta?.notify !== false });
}

/** The v1 QueryClient; `defaults` override the default options (tests). */
export function createQueryClient(defaults: DefaultOptions = {}): QueryClient {
  // "always": offline fails fast as `network` instead of pausing, and a save is never sent later.
  const networkMode = "always";
  // "always" turns refetch on reconnect off; reads still refresh when the connection returns.
  const queries = {
    retry: retryRead,
    networkMode,
    refetchOnReconnect: true,
    throwOnError: throwSelectError,
  } as const;
  return new QueryClient({
    queryCache: new QueryCache({ onError: reportQueryError }),
    mutationCache: new MutationCache({ onError: reportMutationError }),
    defaultOptions: {
      ...defaults,
      queries: { ...queries, ...defaults.queries },
      mutations: { retry: false, networkMode, ...defaults.mutations },
    },
  });
}
