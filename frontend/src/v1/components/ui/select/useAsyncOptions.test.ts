import { act } from "@testing-library/react";
import { renderHookV1 } from "@v1/test";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { SelectOption } from "./options";
import { useAsyncOptions } from "./useAsyncOptions";

type Load = (
  query: string,
  signal: AbortSignal,
) => Promise<readonly SelectOption[]>;

type Call = Readonly<{
  query: string;
  signal: AbortSignal;
  resolve: (options: readonly SelectOption[]) => void;
  reject: (error: unknown) => void;
}>;

/** A loader whose every call waits until the test settles it. */
function deferredLoader() {
  const calls: Call[] = [];
  const load = vi.fn<Load>(
    (query, signal) =>
      new Promise((resolve, reject) => {
        calls.push({ query, signal, resolve, reject });
      }),
  );
  return { load, calls };
}

const opt = (label: string): SelectOption => ({ value: label, label });

type Props = Readonly<{ load?: Load; query: string; enabled: boolean }>;

function setup(initialProps: Props) {
  return renderHookV1(
    (p: Props) => useAsyncOptions(p.load, p.query, p.enabled),
    { initialProps },
  );
}

const advance = (ms: number) => act(() => vi.advanceTimersByTime(ms));

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

it("is empty and idle with no loader", () => {
  const { result } = setup({ query: "a", enabled: true });
  advance(1000);
  expect(result.current).toEqual({ options: [], loading: false, error: null });
});

it("does not load while disabled", () => {
  const { load } = deferredLoader();
  const { result } = setup({ load, query: "", enabled: false });
  advance(1000);
  expect(load).not.toHaveBeenCalled();
  expect(result.current.loading).toBe(false);
});

it("loads at once when enabled, then shows the options", async () => {
  const { load, calls } = deferredLoader();
  const { result } = setup({ load, query: "", enabled: true });
  expect(result.current.loading).toBe(false);
  advance(0);
  expect(load).toHaveBeenCalledTimes(1);
  expect(calls[0].query).toBe("");
  expect(result.current.loading).toBe(true);
  await act(async () => calls[0].resolve([opt("Alpha")]));
  expect(result.current).toEqual({
    options: [opt("Alpha")],
    loading: false,
    error: null,
  });
});

it("debounces query changes by 250ms", async () => {
  const { load, calls } = deferredLoader();
  const { result, rerender } = setup({ load, query: "", enabled: true });
  advance(0);
  await act(async () => calls[0].resolve([]));
  rerender({ load, query: "a", enabled: true });
  advance(100);
  rerender({ load, query: "ab", enabled: true });
  advance(249);
  expect(load).toHaveBeenCalledTimes(1);
  expect(result.current.loading).toBe(false);
  advance(1);
  expect(load).toHaveBeenCalledTimes(2);
  expect(calls[1].query).toBe("ab");
  expect(result.current.loading).toBe(true);
});

it("drops a response for a query that is no longer current", async () => {
  const { load, calls } = deferredLoader();
  const { result, rerender } = setup({ load, query: "a", enabled: true });
  advance(0);
  rerender({ load, query: "ab", enabled: true });
  // "a" settles while "ab" is still waiting out its debounce.
  await act(async () => calls[0].resolve([opt("Alpha")]));
  expect(result.current.options).toEqual([]);
  advance(250);
  await act(async () => calls[1].resolve([opt("Abacus")]));
  expect(result.current.options).toEqual([opt("Abacus")]);
  expect(result.current.loading).toBe(false);
});

it("drops an error for a query that is no longer current", async () => {
  const { load, calls } = deferredLoader();
  const { result, rerender } = setup({ load, query: "a", enabled: true });
  advance(0);
  rerender({ load, query: "ab", enabled: true });
  await act(async () => calls[0].reject(new Error("stale")));
  expect(result.current.error).toBeNull();
});

it("aborts the previous request when the next one starts", async () => {
  const { load, calls } = deferredLoader();
  const { rerender } = setup({ load, query: "a", enabled: true });
  advance(0);
  rerender({ load, query: "ab", enabled: true });
  expect(calls[0].signal.aborted).toBe(false);
  advance(250);
  expect(calls[0].signal.aborted).toBe(true);
  expect(calls[1].signal.aborted).toBe(false);
});

it("ignores the AbortError of a cancelled request", async () => {
  const { load, calls } = deferredLoader();
  const { result, rerender } = setup({ load, query: "a", enabled: true });
  advance(0);
  rerender({ load, query: "ab", enabled: true });
  advance(250);
  await act(async () =>
    calls[0].reject(new DOMException("aborted", "AbortError")),
  );
  expect(result.current.error).toBeNull();
  expect(result.current.loading).toBe(true);
});

it("reports a failed load and stops loading", async () => {
  const { load, calls } = deferredLoader();
  const { result } = setup({ load, query: "", enabled: true });
  advance(0);
  const boom = new Error("boom");
  await act(async () => calls[0].reject(boom));
  expect(result.current.error).toBe(boom);
  expect(result.current.loading).toBe(false);
});

it("wraps a rejection that is not an Error", async () => {
  const { load, calls } = deferredLoader();
  const { result } = setup({ load, query: "", enabled: true });
  advance(0);
  await act(async () => calls[0].reject("nope"));
  expect(result.current.error?.message).toBe("nope");
});

it("clears the error when the next load starts", async () => {
  const { load, calls } = deferredLoader();
  const { result, rerender } = setup({ load, query: "", enabled: true });
  advance(0);
  await act(async () => calls[0].reject(new Error("boom")));
  rerender({ load, query: "a", enabled: true });
  advance(250);
  expect(result.current.error).toBeNull();
  expect(result.current.loading).toBe(true);
});

it("aborts the request in flight on unmount", () => {
  const { load, calls } = deferredLoader();
  const { unmount } = setup({ load, query: "", enabled: true });
  advance(0);
  unmount();
  expect(calls[0].signal.aborted).toBe(true);
});

it("aborts and stops loading when disabled, and loads at once when enabled again", async () => {
  const { load, calls } = deferredLoader();
  const { result, rerender } = setup({ load, query: "", enabled: true });
  advance(0);
  rerender({ load, query: "", enabled: false });
  expect(calls[0].signal.aborted).toBe(true);
  expect(result.current.loading).toBe(false);
  rerender({ load, query: "a", enabled: true });
  advance(0);
  expect(load).toHaveBeenCalledTimes(2);
  expect(calls[1].query).toBe("a");
});
