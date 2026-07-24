import { describe, expect, it, vi } from "vitest";

import { fetchAllPages, unwrapList } from "./pagination";

describe("unwrapList", () => {
  it("returns a bare array unchanged", () => {
    expect(unwrapList({ data: [1, 2] })).toEqual([1, 2]);
  });

  it("unwraps a paginated envelope", () => {
    expect(unwrapList({ data: { count: 2, results: [1, 2] } })).toEqual([1, 2]);
  });

  it("returns [] for anything else", () => {
    expect(unwrapList(undefined)).toEqual([]);
    expect(unwrapList({ data: { detail: "nope" } })).toEqual([]);
  });
});

describe("fetchAllPages", () => {
  it("makes a single request when the endpoint is not paginated", async () => {
    const axiosInstance = vi.fn().mockResolvedValue({ data: [1, 2, 3] });
    await expect(fetchAllPages(axiosInstance, { url: "/x/" })).resolves.toEqual(
      [1, 2, 3],
    );
    expect(axiosInstance).toHaveBeenCalledTimes(1);
  });

  it("follows pages until every row is collected", async () => {
    const axiosInstance = vi
      .fn()
      .mockResolvedValueOnce({ data: { count: 3, results: [1, 2] } })
      .mockResolvedValueOnce({ data: { count: 3, results: [3] } });

    await expect(
      fetchAllPages(axiosInstance, { url: "/x/", params: { type: "LLM" } }),
    ).resolves.toEqual([1, 2, 3]);
    // Later pages must keep the caller's own params alongside ?page.
    expect(axiosInstance.mock.calls[1][0].params).toEqual({
      type: "LLM",
      page: 2,
    });
  });

  it("stops instead of looping when a page adds nothing", async () => {
    const axiosInstance = vi
      .fn()
      .mockResolvedValue({ data: { count: 99, results: [] } });
    await expect(fetchAllPages(axiosInstance, { url: "/x/" })).resolves.toEqual(
      [],
    );
    expect(axiosInstance).toHaveBeenCalledTimes(2);
  });
});
