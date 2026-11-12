import { useMutation, useQuery } from "@tanstack/react-query";
import { act, waitFor } from "@testing-library/react";
import { type NotifyInput, setNotifier } from "@v1/lib/notify";
import {
  adapterKeys,
  adapterQueries,
  listAdapters,
} from "@v1/services/adapters";
import { setOrganizationId } from "@v1/services/context";
import { ApiError } from "@v1/services/errors";
import {
  apiPath,
  DEFAULT_SESSION,
  delay,
  HttpResponse,
  http as mock,
  mockApi,
  renderHookV1,
} from "@v1/test";
import { adapterFixtures, adapterHandlers } from "@v1/test/fixtures/adapters";
import { isCancel } from "axios";
import type { JsonBodyType } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClient, retryRead } from "./query";

const ADAPTERS = apiPath(DEFAULT_SESSION, "/adapter/");
const LLM = { adapterType: "LLM" } as const;

let shown: NotifyInput[];
let unregister: () => void;

beforeEach(() => {
  setOrganizationId(DEFAULT_SESSION.organization.id);
  shown = [];
  unregister = setNotifier({
    show: (input) => {
      shown.push(input);
      return "toast-1";
    },
    dismiss: () => undefined,
  });
});
afterEach(() => {
  unregister();
  setOrganizationId(null);
});

/* A handler that answers `status` and counts its calls. */
function failing(status: number, body: JsonBodyType = {}) {
  const calls = { count: 0 };
  mockApi(
    mock.all(ADAPTERS, () => {
      calls.count += 1;
      return HttpResponse.json(body, {
        status,
        headers: { "X-Request-ID": "req-7" },
      });
    }),
  );
  return calls;
}

describe("retryRead", () => {
  it("retries transient failures up to twice", () => {
    const network = new ApiError({ kind: "network", message: "m" });
    expect(retryRead(0, network)).toBe(true);
    expect(retryRead(1, network)).toBe(true);
    expect(retryRead(2, network)).toBe(false);
    expect(
      retryRead(
        0,
        new ApiError({ kind: "not_found", message: "m", status: 404 }),
      ),
    ).toBe(false);
  });
});

describe("reads", () => {
  it("retry a gateway error, then report it", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const calls = failing(503);
    const queryClient = createQueryClient({ queries: { retryDelay: 0 } });
    const { result } = renderHookV1(() => useQuery(adapterQueries.list(LLM)), {
      queryClient,
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(calls.count).toBe(3);
  });

  it("do not retry a client error", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const calls = failing(404);
    const queryClient = createQueryClient({ queries: { retryDelay: 0 } });
    const { result } = renderHookV1(() => useQuery(adapterQueries.list(LLM)), {
      queryClient,
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(calls.count).toBe(1);
  });

  it("with no data are left to the page and logged with the request id", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    failing(500, { error: "Database down" });
    const { result } = renderHookV1(() => useQuery(adapterQueries.list(LLM)));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(shown).toEqual([]);
    expect(warn).toHaveBeenCalledWith(
      "[v1 api] %s (request %s)",
      "Database down",
      "req-7",
    );
  });

  it("toast when a refresh fails while data is on screen", async () => {
    mockApi(...adapterHandlers(DEFAULT_SESSION));
    const { result } = renderHookV1(() => useQuery(adapterQueries.list(LLM)));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    failing(500, { error: "Database down" });
    await act(() => result.current.refetch());
    expect(shown).toEqual([
      expect.objectContaining({
        title: "Database down",
        requestId: "req-7",
        id: JSON.stringify(adapterQueries.list(LLM).queryKey),
      }),
    ]);
  });

  it("are cancelled when the caller unmounts, and report nothing", async () => {
    mockApi(
      mock.get(ADAPTERS, async () => {
        await delay(100);
        return HttpResponse.json([]);
      }),
    );
    let request: Promise<unknown> | undefined;
    const { unmount } = renderHookV1(() =>
      useQuery({
        queryKey: ["cancel-test"],
        queryFn: ({ signal }) => {
          request = listAdapters(LLM, { signal });
          return request;
        },
      }),
    );
    await waitFor(() => expect(request).toBeDefined());
    unmount();
    const error = await request?.catch((e: unknown) => e);
    expect(isCancel(error)).toBe(true);
    expect(shown).toEqual([]);
  });
});

describe("paging", () => {
  it("keeps the previous page on screen while the next loads", async () => {
    mockApi(...adapterHandlers(DEFAULT_SESSION));
    const name = (data?: { results: readonly { adapter_name: string }[] }) =>
      data?.results[0]?.adapter_name;
    const { result, rerender } = renderHookV1(
      ({ page }: { page: number }) =>
        useQuery(adapterQueries.page({ ...LLM, page, pageSize: 1 })),
      { initialProps: { page: 1 } },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(name(result.current.data)).toBe("OpenAI GPT-4o");
    rerender({ page: 2 });
    expect(result.current.isPlaceholderData).toBe(true);
    expect(name(result.current.data)).toBe("OpenAI GPT-4o");
    await waitFor(() => expect(result.current.isPlaceholderData).toBe(false));
    expect(name(result.current.data)).toBe("Claude");
  });
});

describe("invalidation", () => {
  it("refetches a resource's queries in this organisation only", async () => {
    const seen: URL[] = [];
    mockApi(...adapterHandlers(DEFAULT_SESSION, adapterFixtures.llm, seen));
    const otherOrg = ["org-2", "adapters", "list", LLM] as const;
    const { result, queryClient } = renderHookV1(() => [
      useQuery(adapterQueries.list(LLM)),
      useQuery(adapterQueries.page({ ...LLM, page: 1, pageSize: 10 })),
    ]);
    await waitFor(() =>
      expect(result.current.every((query) => query.isSuccess)).toBe(true),
    );
    queryClient.setQueryData(otherOrg, []);
    await act(() =>
      queryClient.invalidateQueries({ queryKey: adapterKeys.all() }),
    );
    expect(seen).toHaveLength(4);
    expect(queryClient.getQueryState(otherOrg)?.isInvalidated).toBe(false);
  });
});

describe("mutations", () => {
  const save = () => listAdapters(LLM);

  it("toast a failure with its request id", async () => {
    failing(409, { detail: "Already exists." });
    const { result } = renderHookV1(() => useMutation({ mutationFn: save }));
    await act(() => result.current.mutateAsync().catch(() => undefined));
    expect(shown).toEqual([
      expect.objectContaining({
        kind: "error",
        title: "Already exists.",
        requestId: "req-7",
      }),
    ]);
  });

  it("only log when the form shows the error itself", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    failing(400, { type: "validation_error", errors: [] });
    const { result } = renderHookV1(() =>
      useMutation({ mutationFn: save, meta: { notify: false } }),
    );
    await act(() => result.current.mutateAsync().catch(() => undefined));
    expect(shown).toEqual([]);
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it("fail on network loss without retrying", async () => {
    const calls = { count: 0 };
    mockApi(
      mock.get(ADAPTERS, () => {
        calls.count += 1;
        return HttpResponse.error();
      }),
    );
    const { result } = renderHookV1(() => useMutation({ mutationFn: save }), {
      queryClient: createQueryClient(),
    });
    await act(() => result.current.mutateAsync().catch(() => undefined));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toMatchObject({ kind: "network" });
    expect(calls.count).toBe(1);
    expect(shown).toHaveLength(1);
  });
});
