import { useEffect, useRef, useState } from "react";
import type { SelectOption } from "./options";

export type AsyncState = Readonly<{
  options: readonly SelectOption[];
  loading: boolean;
  error: Error | null;
}>;

/** Fetches the options for `query`; aborted through `signal` when superseded. */
export type LoadOptions = (
  query: string,
  signal: AbortSignal,
) => Promise<readonly SelectOption[]>;

const IDLE: AsyncState = { options: [], loading: false, error: null };

/**
 * Options fetched by `load` for `query` while `enabled` (the list is open).
 * A query change waits `debounceMs`; the first load after `enabled` turns
 * true runs at once. Each load aborts the one before it, a response for a
 * query that is no longer current is dropped, and unmounting aborts.
 * `load` is read from a ref, so a new function identity (an inline arrow)
 * neither refetches nor cancels.
 */
export function useAsyncOptions(
  load: LoadOptions | undefined,
  query: string,
  enabled: boolean,
  debounceMs = 250,
): AsyncState {
  const [state, setState] = useState<AsyncState>(IDLE);
  const latestQuery = useRef(query);
  latestQuery.current = query;
  const latestLoad = useRef(load);
  latestLoad.current = load;
  const hasLoad = load !== undefined;
  const controller = useRef<AbortController | null>(null);
  const first = useRef(true);

  useEffect(() => {
    if (!hasLoad || !enabled) {
      first.current = true;
      if (controller.current) {
        controller.current.abort();
        controller.current = null;
        setState((current) => ({ ...current, loading: false }));
      }
      return;
    }
    const delay = first.current ? 0 : debounceMs;
    first.current = false;
    const timer = setTimeout(() => {
      const fetchOptions = latestLoad.current;
      if (!fetchOptions) {
        return;
      }
      controller.current?.abort();
      const own = new AbortController();
      controller.current = own;
      setState((current) => ({ ...current, loading: true, error: null }));
      const current = () =>
        !own.signal.aborted && query === latestQuery.current;
      fetchOptions(query, own.signal).then(
        (options) => {
          if (current()) {
            setState({ options, loading: false, error: null });
          }
        },
        (error: unknown) => {
          // Our own aborts fail `current()`; any other rejection is an error.
          if (!current()) {
            return;
          }
          setState((previous) => ({
            ...previous,
            loading: false,
            error: error instanceof Error ? error : new Error(String(error)),
          }));
        },
      );
    }, delay);
    return () => clearTimeout(timer);
  }, [hasLoad, query, enabled, debounceMs]);

  useEffect(() => () => controller.current?.abort(), []);

  return load ? state : IDLE;
}
