import type { QueryClient } from "@tanstack/react-query";
import { setOrganizationId } from "@v1/services/context";
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
  engine = createRunEngine({
    store,
    channel,
    queryClient,
    client: client as unknown as RunClient,
    notify: (input) => {
      notified.push({ kind: input.kind, title: input.title });
    },
    report: () => {
      notified.push({ kind: "error", title: "request failed" });
    },
    newRunId: () => {
      counter += 1;
      return `run-${counter}`;
    },
  });
});

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
    // No stale timer was armed.
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

  it("clears the status and reports a failed request", async () => {
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    pending[0]?.reject(new Error("boom"));
    await flush();
    expect(entry()).toBeUndefined();
    expect(notified[0]?.kind).toBe("error");
    expect(store.getState().active).toBe(0);
  });
});

describe("stale runs", () => {
  it("fails a run with no result after sixteen minutes", async () => {
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
  });

  it("does not let an earlier run's timer touch a newer run", async () => {
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
    // The first run finished; the user runs again.
    channel.emit(RUN_RESULT_EVENT, completedEvent({ run_id: "run-1" }));
    engine.run(plan);
    pending[1]?.resolve(accepted("run-2"));
    await flush();
    await vi.advanceTimersByTimeAsync(STALE_RUN_MS / 2);
    expect(entry()).toMatchObject({ status: "running", runId: "run-2" });
    expect(notified.filter((n) => n.kind === "warning")).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(STALE_RUN_MS / 2);
    expect(entry()).toMatchObject({ status: "failed", runId: "run-2" });
  });

  it("cancels the timer when the result arrives", async () => {
    engine.run({
      toolId: TOOL_ID,
      promptIds: ["p1"],
      profileIds: ["profile-1"],
      documentIds: ["doc-1"],
    });
    pending[0]?.resolve(accepted("run-1"));
    await flush();
    channel.emit(RUN_RESULT_EVENT, failedEvent({ run_id: "run-1" }));
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

  it("names the operation when a failed event has no message", () => {
    channel.emit(
      RUN_RESULT_EVENT,
      failedEvent({ run_id: "run-1", error: null, error_details: null }),
    );
    expect(entry()?.failure).toEqual({
      message: "fetch_response failed",
      provider: null,
      requestId: null,
      retryAfterSeconds: null,
    });
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

  it("takes the old synchronous rows as the result", async () => {
    const rows = [outputRow({ is_single_pass_extract: true })];
    queryClient.setQueryData(
      promptOutputKeys.list({ toolId: TOOL_ID, singlePass: true }),
      [] as PromptOutput[],
    );
    client.runSinglePass.mockResolvedValueOnce(rows);
    engine.runSinglePass({ toolId: TOOL_ID, documentId: "doc-1" });
    await flush();
    expect(store.getState().singlePass[key]?.status).toBe("completed");
    expect(
      queryClient.getQueryData(
        promptOutputKeys.list({ toolId: TOOL_ID, singlePass: true }),
      ),
    ).toEqual(rows);
  });

  it("drops the run when pending or when the request fails", async () => {
    client.runSinglePass.mockResolvedValueOnce({ status: "pending" });
    engine.runSinglePass({ toolId: TOOL_ID, documentId: "doc-1" });
    await flush();
    expect(store.getState().singlePass[key]).toBeUndefined();
    client.runSinglePass.mockRejectedValueOnce(new Error("boom"));
    engine.runSinglePass({ toolId: TOOL_ID, documentId: "doc-1" });
    await flush();
    expect(store.getState().singlePass[key]).toBeUndefined();
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
