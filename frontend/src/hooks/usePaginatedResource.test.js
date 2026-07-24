import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { usePaginatedResource } from "./usePaginatedResource";

const page = (results, count) => ({ data: { count, results } });

const deferred = () => {
  let resolve;
  const promise = new Promise((r) => {
    resolve = r;
  });
  return { promise, resolve };
};

describe("usePaginatedResource", () => {
  it("loads the first page and records the total", async () => {
    const request = vi.fn().mockResolvedValue(page(["a", "b"], 5));
    const { result } = renderHook(() => usePaginatedResource({ request }));

    await act(() => result.current.fetchPage(1, 2, ""));

    expect(request).toHaveBeenCalledWith({ page: 1, page_size: 2 });
    expect(result.current.items).toEqual(["a", "b"]);
    expect(result.current.pagination).toMatchObject({ current: 1, total: 5 });
    expect(result.current.isLoading).toBe(false);
  });

  it("passes a search term through and omits it when blank", async () => {
    const request = vi.fn().mockResolvedValue(page([], 0));
    const { result } = renderHook(() => usePaginatedResource({ request }));

    await act(() => result.current.fetchPage(1, 10, "abc"));
    expect(request).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 10,
      search: "abc",
    });

    await act(() => result.current.fetchPage(1, 10, ""));
    expect(request).toHaveBeenLastCalledWith({ page: 1, page_size: 10 });
  });

  it("steps back a page when the requested one came back empty", async () => {
    const request = vi
      .fn()
      .mockResolvedValueOnce(page([], 2))
      .mockResolvedValueOnce(page(["a", "b"], 2));
    const { result } = renderHook(() => usePaginatedResource({ request }));

    await act(() => result.current.fetchPage(2, 2, ""));

    expect(request).toHaveBeenLastCalledWith({ page: 1, page_size: 2 });
    expect(result.current.items).toEqual(["a", "b"]);
    expect(result.current.pagination).toMatchObject({ current: 1 });
  });

  it("keeps loading true until the step-back request resolves", async () => {
    const second = deferred();
    const request = vi
      .fn()
      .mockResolvedValueOnce(page([], 2))
      .mockReturnValueOnce(second.promise);
    const { result } = renderHook(() => usePaginatedResource({ request }));

    let done;
    act(() => {
      done = result.current.fetchPage(2, 2, "");
    });
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    expect(result.current.isLoading).toBe(true);

    await act(async () => {
      second.resolve(page(["a"], 2));
      await done;
    });
    expect(result.current.isLoading).toBe(false);
    // Awaiting the call must mean the replacement page is already in state,
    // so callers that chain off refresh() see the rows they asked for.
    expect(result.current.items).toEqual(["a"]);
  });

  it("ignores a superseded response that resolves late", async () => {
    const slow = deferred();
    const request = vi
      .fn()
      .mockReturnValueOnce(slow.promise)
      .mockResolvedValueOnce(page(["new"], 1));
    const { result } = renderHook(() => usePaginatedResource({ request }));

    let stale;
    act(() => {
      stale = result.current.fetchPage(1, 10, "old");
    });
    await act(() => result.current.fetchPage(1, 10, "new"));
    expect(result.current.items).toEqual(["new"]);

    await act(async () => {
      slow.resolve(page(["old"], 1));
      await stale;
    });
    expect(result.current.items).toEqual(["new"]);
  });

  it("reports errors without clobbering the current rows", async () => {
    const onError = vi.fn();
    const request = vi
      .fn()
      .mockResolvedValueOnce(page(["a"], 1))
      .mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() =>
      usePaginatedResource({ request, onError }),
    );

    await act(() => result.current.fetchPage(1, 10, ""));
    await act(() => result.current.fetchPage(2, 10, ""));

    expect(onError).toHaveBeenCalledTimes(1);
    expect(result.current.items).toEqual(["a"]);
    expect(result.current.isLoading).toBe(false);
  });
});
