import { useEffect, useRef, useState } from "react";
import type { SelectOption } from "./options";

export type AsyncState = Readonly<{
  options: readonly SelectOption[];
  loading: boolean;
  error: Error | null;
}>;

type Load = (
  query: string,
  signal: AbortSignal,
) => Promise<readonly SelectOption[]>;

const IDLE: AsyncState = { options: [], loading: false, error: null };

const isAbort = (error: unknown): boolean =>
  typeof error === "object" &&
  error !== null &&
  (error as { name?: unknown }).name === "AbortError";

/**
 * Options fetched by `load` for `query` while `enabled` (the list is open).
 * A query change waits `debounceMs`; the first load after `enabled` turns
 * true runs at once. Each load aborts the one before it, a response for a
 * query that is no longer current is dropped, and unmounting aborts.
 */
export function useAsyncOptions(
  load: Load | undefined,
  query: string,
  enabled: boolean,
  debounceMs = 250,
): AsyncState {
  const [state, setState] = useState<AsyncState>(IDLE);
  const latestQuery = useRef(query);
  const controller = useRef<AbortController | null>(null);
  const first = useRef(true);

  useEffect(() => {
    latestQuery.current = query;
  }, [query]);

  useEffect(() => {
    if (!load || !enabled) {
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
      controller.current?.abort();
      const own = new AbortController();
      controller.current = own;
      setState((current) => ({ ...current, loading: true, error: null }));
      const current = () =>
        !own.signal.aborted && query === latestQuery.current;
      load(query, own.signal).then(
        (options) => {
          if (current()) {
            setState({ options, loading: false, error: null });
          }
        },
        (error: unknown) => {
          if (isAbort(error) || !current()) {
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
  }, [load, query, enabled, debounceMs]);

  useEffect(() => () => controller.current?.abort(), []);

  return load ? state : IDLE;
}
