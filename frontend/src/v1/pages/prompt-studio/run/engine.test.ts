import type { QueryClient } from "@tanstack/react-query";
import { setOrganizationId } from "@v1/services/context";
import { ApiError } from "@v1/services/errors";
import {
  type PromptOutput,
  promptOutputKeys,
} from "@v1/services/promptOutputs";
import {
  RUN_RESULT_EVENT,
  RUN_STARTED_EVENT,
  type RunResponse,
} from "@v1/services/promptRuns";
import {
  createPromptRunStore,
  type RunStore,
  runKey,
  singlePassKey,
  TIMEOUT_MESSAGE,
} from "@v1/stores/promptRuns";
import { createTestQueryClient, DEFAULT_SESSION } from "@v1/test";
import {
  completedEvent,
  failedEvent,
  outputRow,
  startedEvent,
  TOOL_ID,
} from "@v1/test/fixtures/promptRuns";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createLocalRunChannel, type LocalRunChannel } from "./channel";
import {
  createRunEngine,
  PENDING_MESSAGE,
  type RunClient,
  type RunEngine,
  STALE_RUN_MS,
} from "./engine";

type Deferred = {
  resolve: (value: RunResponse) => void;
  reject: (error: unknown) => void;
};

let store: RunStore;
let channel: LocalRunChannel;
let queryClient: QueryClient;
let engine: RunEngine;
let pending: Deferred[];
let client: { [K in keyof RunClient]: ReturnType<typeof vi.fn> };
let notified: { kind: string; title: string }[];
let toastIds: (string | undefined)[];
let counter = 0;

const accepted = (runId: string): RunResponse => ({
  status: "accepted",
  task_id: `task-${runId}`,
  run_id: runId,
});

function deferredCall() {
  return () =>
    new Promise<RunResponse>((resolve, reject) => {
      pending.push({ resolve, reject });
    });
}

const flush = () => vi.advanceTimersByTimeAsync(0);

beforeEach(() => {
  vi.useFakeTimers({ now: 1_000 });
  setOrganizationId(DEFAULT_SESSION.organization.id);
  notified = [];
  toastIds = [];
  store = createPromptRunStore();
  channel = createLocalRunChannel();
  queryClient = createTestQueryClient();
  pending = [];
  client = {
    runPrompt: vi.fn(deferredCall()),
    runPrompts: vi.fn(deferredCall()),
    runSinglePass: vi.fn(deferredCall()),
  };
  counter = 0;
  engine = makeEngine();
});

function makeEngine(): RunEngine {
  return createRunEngine({
    store,
    channel,
    queryClient,
    client: client as unknown as RunClient,
    notify: (input) => {
      notified.push({ kind: input.kind, title: input.title });
      toastIds.push(input.id);
    },
    report: () => {
      notified.push({ kind: "error", title: "request failed" });
    },
    newRunId: () => {
      counter += 1;
      return `run-${counter}`;
    },
  });
}

afterEach(() => {
  engine.dispose();
  vi.useRealTimers();
  setOrganizationId(null);
});

const entry = (documentId = "doc-1", promptId = "p1") =>
  store.getState().entries[runKey(promptId, documentId, "profile-1")];

describe("queue", () => {
  it("keeps at most five requests in flight and sends the rest in order", async () => {
    const documentIds = Array.from({ length: 7 }, (_, i) => `doc-${i}`);
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds,
    });
    expect(client.runPrompt).toHaveBeenCalledTimes(5);
    expect(store.getState().queue).toHaveLength(2);
    expect(entry("doc-5")?.status).toBe("queued");

    pending[0]?.resolve(accepted("run-1"));
    await flush();
    expect(client.runPrompt).toHaveBeenCalledTimes(6);
    expect(client.runPrompt.mock.calls[5]?.[0]).toMatchObject({
      documentId: "doc-5",
      promptId: "p1",
      runId: "run-6",
    });
    expect(store.getState().active).toBe(5);

    for (const call of pending.slice(1)) {
      call.resolve(accepted("x"));
    }
    await flush();
    expect(client.runPrompt).toHaveBeenCalledTimes(7);
    pending[6]?.resolve(accepted("run-7"));
    await flush();
    expect(store.getState().active).toBe(0);
  });

  it("sends several prompts as one bulk request per document and profile", () => {
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1", "p2"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    expect(client.runPrompts).toHaveBeenCalledWith(
      expect.objectContaining({ promptIds: ["p1", "p2"], documentId: "doc-1" }),
    );
    expect(client.runPrompt).not.toHaveBeenCalled();
  });

  it("does nothing for an empty plan", () => {
    engine.run({
      toolId: TOOL_ID,
      promptIds: [],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    expect(store.getState().queue).toEqual([]);
  });
});

describe("responses", () => {
  it("clears the status and says so when the document is still indexing", async () => {
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    pending[0]?.resolve({ status: "pending", message: null });
    await flush();
    expect(entry()).toBeUndefined();
    expect(notified).toContainEqual({ kind: "info", title: PENDING_MESSAGE });
    expect(store.getState().active).toBe(0);
    expect(toastIds).toEqual(["prompt-run-pending"]);
    // Nothing is left to time out.
    await vi.advanceTimersByTimeAsync(STALE_RUN_MS);
    expect(notified).toHaveLength(1);
  });

  it("uses the backend's pending message when it sends one", async () => {
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    pending[0]?.resolve({
      status: "pending",
      message: "Document is being indexed",
    });
    await flush();
    expect(notified[0]?.title).toBe("Document is being indexed");
  });

  it("marks the run failed and reports a failed request", async () => {
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    pending[0]?.reject(
      new ApiError({
        kind: "server",
        message: "Server error",
        requestId: "r-9",
      }),
    );
    await flush();
    expect(entry()).toMatchObject({
      status: "failed",
      failure: { message: "Server error", requestId: "r-9" },
    });
    expect(notified[0]?.kind).toBe("error");
    expect(store.getState().active).toBe(0);
  });
});

describe("stale runs", () => {
  it("waits sixteen minutes, longer than the LLM adapter's 900 s timeout", () => {
    expect(STALE_RUN_MS).toBe(960_000);
  });

  it("fails a run with no result after sixteen minutes, and refetches its outputs", async () => {
    const list = promptOutputKeys.list({ toolId: TOOL_ID, singlePass: false });
    queryClient.setQueryData(list, [] as PromptOutput[]);
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    pending[0]?.resolve(accepted("run-1"));
    await flush();
    await vi.advanceTimersByTimeAsync(STALE_RUN_MS - 1);
    expect(entry()?.status).toBe("running");
    await vi.advanceTimersByTimeAsync(1);
    expect(entry()?.status).toBe("failed");
    expect(notified).toContainEqual({
      kind: "warning",
      title: TIMEOUT_MESSAGE,
    });
    expect(queryClient.getQueryState(list)?.isInvalidated).toBe(true);
  });

  it("times a run again from its new dispatch", async () => {
    const plan = {
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    };
    engine.run(plan);
    pending[0]?.resolve(accepted("run-1"));
    await flush();
    await vi.advanceTimersByTimeAsync(STALE_RUN_MS / 2);
    // Run again while the first run is still in flight.
    engine.run(plan);
    pending[1]?.resolve(accepted("run-2"));
    await flush();
    await vi.advanceTimersByTimeAsync(STALE_RUN_MS / 2);
    expect(entry()).toMatchObject({ status: "running", runId: "run-2" });
    expect(notified.filter((n) => n.kind === "warning")).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(STALE_RUN_MS / 2);
    expect(entry()).toMatchObject({ status: "failed", runId: "run-2" });
  });

  it("leaves a run alone once its result arrived", async () => {
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    pending[0]?.resolve(accepted("run-1"));
    await flush();
    channel.emit(RUN_RESULT_EVENT, failedEvent({ run_id: "run-1" }));
    await vi.advanceTimersByTimeAsync(STALE_RUN_MS);
    expect(notified.filter((n) => n.kind === "warning")).toHaveLength(0);
  });

  it("expires a run whose request never answers", async () => {
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    await vi.advanceTimersByTimeAsync(STALE_RUN_MS);
    expect(entry()?.status).toBe("failed");
  });

  it("expires a run first seen through a started event, from the server's start", async () => {
    channel.emit(
      RUN_STARTED_EVENT,
      startedEvent({
        run_id: "tab-2",
        started_at: new Date(1_000).toISOString(),
      }),
    );
    await vi.advanceTimersByTimeAsync(STALE_RUN_MS - 1);
    expect(entry()?.status).toBe("running");
    await vi.advanceTimersByTimeAsync(1);
    expect(entry()?.status).toBe("failed");
  });

  it("expires a run whose result event settled nothing", async () => {
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    pending[0]?.resolve(accepted("run-1"));
    await flush();
    channel.emit(
      RUN_RESULT_EVENT,
      failedEvent({ run_id: "run-1", prompt_ids: [] }),
    );
    expect(entry()?.status).toBe("running");
    await vi.advanceTimersByTimeAsync(STALE_RUN_MS);
    expect(entry()?.status).toBe("failed");
  });

  it("expires, through a new engine, the runs a disposed one left", async () => {
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    pending[0]?.resolve(accepted("run-1"));
    await flush();
    engine.dispose();
    engine = makeEngine();
    await vi.advanceTimersByTimeAsync(STALE_RUN_MS);
    expect(entry()?.status).toBe("failed");
  });

  it("stops checking for stale runs when disposed", async () => {
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    pending[0]?.resolve(accepted("run-1"));
    await flush();
    engine.dispose();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("events", () => {
  beforeEach(async () => {
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    pending[0]?.resolve(accepted("run-1"));
    await flush();
  });

  it("keeps the dispatch time when the started event arrives", () => {
    vi.advanceTimersByTime(300);
    channel.emit(RUN_STARTED_EVENT, startedEvent({ run_id: "run-1" }));
    expect(entry()).toMatchObject({ status: "running", startedAt: 1_000 });
  });

  it("resumes a run started elsewhere from the server's start time", () => {
    channel.emit(
      RUN_STARTED_EVENT,
      startedEvent({
        run_id: "tab-2",
        document_id: "doc-9",
        started_at: "2026-11-24T09:15:02.000Z",
      }),
    );
    expect(entry("doc-9")?.startedAt).toBe(
      Date.parse("2026-11-24T09:15:02.000Z"),
    );
  });

  it("maps a failed event, request id and retry hint included", () => {
    channel.emit(RUN_RESULT_EVENT, failedEvent({ run_id: "run-1" }));
    expect(entry()).toMatchObject({
      status: "failed",
      failure: {
        provider: "azure",
        requestId: "8f3a-21c9-4d10",
        retryAfterSeconds: 60,
      },
    });
    expect(notified.at(-1)?.kind).toBe("error");
  });

  it("says the run failed when a failed event has no message", () => {
    channel.emit(
      RUN_RESULT_EVENT,
      failedEvent({ run_id: "run-1", error: null, error_details: null }),
    );
    expect(entry()?.failure).toEqual({
      message: "Prompt run failed.",
      provider: null,
      requestId: null,
      retryAfterSeconds: null,
    });
  });

  it("ignores a started event that trails the run's result", async () => {
    channel.emit(RUN_RESULT_EVENT, failedEvent({ run_id: "run-1" }));
    channel.emit(RUN_STARTED_EVENT, startedEvent({ run_id: "run-1" }));
    expect(entry()?.status).toBe("failed");
  });

  it("starts the timer on the client clock when started_at is unreadable", () => {
    channel.emit(
      RUN_STARTED_EVENT,
      startedEvent({
        run_id: "tab-2",
        document_id: "doc-9",
        started_at: "soon",
      }),
    );
    expect(entry("doc-9")?.startedAt).toBe(Date.now());
  });

  it("settles a run whose inline outputs cannot be read, and refetches", () => {
    const list = promptOutputKeys.list({ toolId: TOOL_ID, singlePass: false });
    queryClient.setQueryData(list, [] as PromptOutput[]);
    channel.emit(
      RUN_RESULT_EVENT,
      completedEvent({ run_id: "run-1", outputs: [{ output: 5 }] }),
    );
    expect(entry()?.status).toBe("completed");
    expect(queryClient.getQueryState(list)?.isInvalidated).toBe(true);
  });

  it("treats an empty run id as missing, so the in-flight run still settles", () => {
    channel.emit(RUN_RESULT_EVENT, failedEvent({ run_id: "" }));
    expect(entry()?.status).toBe("failed");
  });

  it("keeps a failure toast apart from success toasts", () => {
    channel.emit(RUN_RESULT_EVENT, failedEvent({ run_id: "run-1" }));
    channel.emit(RUN_RESULT_EVENT, completedEvent({ run_id: "other" }));
    expect(toastIds).toEqual(["prompt-run-failed", "prompt-run-completed"]);
  });

  it("ignores payloads that are not run events", () => {
    channel.emit(
      RUN_RESULT_EVENT,
      completedEvent({ operation: "index_document" }),
    );
    channel.emit(RUN_STARTED_EVENT, { nope: true });
    expect(entry()?.status).toBe("running");
  });

  it("stops listening when disposed", () => {
    engine.dispose();
    channel.emit(RUN_RESULT_EVENT, completedEvent({ run_id: "run-1" }));
    expect(entry()?.status).toBe("running");
  });
});

describe("outputs", () => {
  const docList = { toolId: TOOL_ID, documentId: "doc-1", singlePass: false };
  const otherTool = { toolId: "tool-2" };

  beforeEach(() => {
    queryClient.setQueryData(promptOutputKeys.list(docList), [
      outputRow({ output: "old" }),
    ]);
    queryClient.setQueryData(
      promptOutputKeys.list(otherTool),
      [] as PromptOutput[],
    );
  });

  it("merges inline outputs into the cached lists of that tool", () => {
    channel.emit(
      RUN_RESULT_EVENT,
      completedEvent({ outputs: [outputRow({ output: "INV-0042" })] }),
    );
    expect(
      queryClient
        .getQueryData<PromptOutput[]>(promptOutputKeys.list(docList))
        ?.map((row) => row.output),
    ).toEqual(["INV-0042"]);
    expect(queryClient.getQueryData(promptOutputKeys.list(otherTool))).toEqual(
      [],
    );
    expect(notified.at(-1)).toEqual({
      kind: "success",
      title: "Prompt execution completed successfully.",
    });
  });

  it("skips a list that has no data yet", () => {
    const loading = promptOutputKeys.list({
      toolId: TOOL_ID,
      documentId: "doc-2",
      singlePass: false,
    });
    queryClient.getQueryCache().build(queryClient, { queryKey: loading });
    channel.emit(
      RUN_RESULT_EVENT,
      completedEvent({ outputs: [outputRow({ output: "INV-0042" })] }),
    );
    expect(queryClient.getQueryData(loading)).toBeUndefined();
    expect(notified.at(-1)?.kind).toBe("success");
  });

  it("refetches instead of merging while one of the tool's lists is loading", () => {
    void queryClient.prefetchQuery({
      queryKey: promptOutputKeys.list({ toolId: TOOL_ID, singlePass: true }),
      queryFn: () => new Promise<PromptOutput[]>(() => undefined),
    });
    channel.emit(
      RUN_RESULT_EVENT,
      completedEvent({ outputs: [outputRow({ output: "INV-0042" })] }),
    );
    expect(
      queryClient
        .getQueryData<PromptOutput[]>(promptOutputKeys.list(docList))
        ?.map((row) => row.output),
    ).toEqual(["old"]);
    expect(
      queryClient.getQueryState(promptOutputKeys.list(docList))?.isInvalidated,
    ).toBe(true);
  });

  it("marks the tool's lists stale when the event carries no outputs", () => {
    channel.emit(RUN_RESULT_EVENT, completedEvent({ outputs: null }));
    expect(
      queryClient.getQueryState(promptOutputKeys.list(docList))?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState(promptOutputKeys.list(otherTool))
        ?.isInvalidated,
    ).toBe(false);
  });
});

describe("single pass", () => {
  const key = singlePassKey(TOOL_ID, "doc-1");

  it("runs one request outside the queue and settles from the socket", async () => {
    engine.runSinglePass({ toolId: TOOL_ID, documentId: "doc-1" });
    expect(client.runSinglePass).toHaveBeenCalledWith({
      toolId: TOOL_ID,
      documentId: "doc-1",
      runId: "run-1",
    });
    expect(store.getState().active).toBe(0);
    pending[0]?.resolve(accepted("run-1"));
    await flush();
    channel.emit(
      RUN_RESULT_EVENT,
      completedEvent({
        operation: "single_pass_extraction",
        run_id: "run-1",
        elapsed: 9,
      }),
    );
    expect(store.getState().singlePass[key]).toMatchObject({
      status: "completed",
      elapsedSeconds: 9,
    });
    expect(notified.at(-1)?.title).toBe(
      "Single pass extraction completed successfully.",
    );
  });

  it("drops the run when pending, and fails it when the request fails", async () => {
    client.runSinglePass.mockResolvedValueOnce({ status: "pending" });
    engine.runSinglePass({ toolId: TOOL_ID, documentId: "doc-1" });
    await flush();
    expect(store.getState().singlePass[key]).toBeUndefined();
    client.runSinglePass.mockRejectedValueOnce(new Error("boom"));
    engine.runSinglePass({ toolId: TOOL_ID, documentId: "doc-1" });
    await flush();
    expect(store.getState().singlePass[key]?.status).toBe("failed");
    expect(notified.map((n) => n.kind)).toEqual(["info", "error"]);
  });

  it("times out a single-pass run with no result", async () => {
    engine.runSinglePass({ toolId: TOOL_ID, documentId: "doc-1" });
    pending[0]?.resolve(accepted("run-1"));
    await flush();
    await vi.advanceTimersByTimeAsync(STALE_RUN_MS);
    expect(store.getState().singlePass[key]?.status).toBe("failed");
  });
});
