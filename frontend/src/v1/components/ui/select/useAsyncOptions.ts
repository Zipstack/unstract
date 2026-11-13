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
const STARTING: AsyncState = { options: [], loading: true, error: null };

/**
 * Options fetched by `load` for `query` while `enabled` (the list is open).
 * A query change drops the options at once, so the previous query's results
 * are neither shown nor selectable while the next load waits out
 * `debounceMs`; the first load after `enabled` turns true runs at once. In
 * both cases `loading` is true from that render on, so an empty list never
 * shows before a load. Turning `enabled` false aborts and drops the options
 * and the error, so a reopened list shows nothing stale. Each load aborts the
 * one before it, a response for a query that is no longer current is dropped,
 * a failed load empties the options, and unmounting aborts. `load` is read
 * from a ref, so a new function identity (an inline arrow) neither refetches
 * nor cancels.
 */
export function useAsyncOptions(
  load: LoadOptions | undefined,
  query: string,
  enabled: boolean,
  debounceMs = 250,
): AsyncState {
  const hasLoad = load !== undefined;
  const active = hasLoad && enabled;
  const [state, setState] = useState<AsyncState>(active ? STARTING : IDLE);
  // Adjusting state while rendering, React's pattern for "on prop change":
  // a change of `active`, or of the query while active, resets the state.
  const [seen, setSeen] = useState({ active, query });
  if (active !== seen.active || (active && query !== seen.query)) {
    setSeen({ active, query });
    setState(active ? STARTING : IDLE);
  }
  const latestQuery = useRef(query);
  latestQuery.current = query;
  const latestLoad = useRef(load);
  latestLoad.current = load;
  const controller = useRef<AbortController | null>(null);
  const first = useRef(true);

  useEffect(() => {
    if (!hasLoad || !enabled) {
      first.current = true;
      controller.current?.abort();
      controller.current = null;
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
          // Our own aborts fail `current()`; any other rejection is an error,
          // and the previous query's options must not stay selectable.
          if (!current()) {
            return;
          }
          setState({
            options: [],
            loading: false,
            error: error instanceof Error ? error : new Error(String(error)),
          });
        },
      );
    }, delay);
    return () => clearTimeout(timer);
  }, [hasLoad, query, enabled, debounceMs]);

  useEffect(() => () => controller.current?.abort(), []);

  return load ? state : IDLE;
}
