import { describe, expect, it } from "vitest";
import {
  createPromptRunStore,
  EMPTY_RUN_STATE,
  enqueueRuns,
  expireRun,
  MAX_ACTIVE_REQUESTS,
  markRunCompleted,
  markRunFailed,
  markRunStarted,
  planRun,
  type RunFailure,
  type RunRequest,
  type RunSignal,
  type RunState,
  releaseRequest,
  removeRun,
  runKey,
  singlePassKey,
  TIMEOUT_MESSAGE,
  takeNextRequests,
} from "./promptRuns";

const ids = (() => {
  let n = 0;
  return () => {
    n += 1;
    return `run-${n}`;
  };
})();

const request = (overrides: Partial<RunRequest> = {}): RunRequest => ({
  runId: ids(),
  toolId: "tool-1",
  documentId: "doc-1",
  profileId: "profile-1",
  promptIds: ["p1"],
  ...overrides,
});

const signal = (overrides: Partial<RunSignal> = {}): RunSignal => ({
  toolId: "tool-1",
  runId: null,
  promptIds: ["p1"],
  documentId: "doc-1",
  profileId: "profile-1",
  singlePass: false,
  ...overrides,
});

const failure: RunFailure = {
  message: "Rate limit exceeded",
  provider: "azure",
  requestId: "8f3a-21c9-4d10",
  retryAfterSeconds: 60,
};

const entry = (state: RunState, promptId = "p1", documentId = "doc-1") =>
  state.entries[runKey(promptId, documentId, "profile-1")];

describe("planRun", () => {
  it("makes one request per prompt, profile and document for one prompt", () => {
    const requests = planRun({
      toolId: "tool-1",
      promptIds: ["p1"],
      profileIds: ["a", "b"],
      documentIds: ["d1", "d2"],
      newRunId: ids,
    });
    expect(
      requests.map((r) => [r.promptIds, r.profileId, r.documentId]),
    ).toEqual([
      [["p1"], "a", "d1"],
      [["p1"], "a", "d2"],
      [["p1"], "b", "d1"],
      [["p1"], "b", "d2"],
    ]);
    expect(new Set(requests.map((r) => r.runId)).size).toBe(4);
  });

  it("makes one bulk request per profile and document for several prompts", () => {
    const requests = planRun({
      toolId: "tool-1",
      promptIds: ["p1", "p2"],
      profileIds: ["a"],
      documentIds: ["d1", "d2"],
      newRunId: ids,
    });
    expect(requests.map((r) => [r.promptIds, r.documentId])).toEqual([
      [["p1", "p2"], "d1"],
      [["p1", "p2"], "d2"],
    ]);
  });

  it("plans nothing when an axis is empty", () => {
    expect(
      planRun({
        toolId: "tool-1",
        promptIds: ["p1"],
        profileIds: [],
        documentIds: ["d1"],
        newRunId: ids,
      }),
    ).toEqual([]);
  });
});

describe("queue", () => {
  it("never has more than five requests active, and drains first in, first out", () => {
    const requests = Array.from({ length: 8 }, (_, i) =>
      request({ documentId: `doc-${i}` }),
    );
    let state = enqueueRuns(EMPTY_RUN_STATE, requests);
    expect(state.queue).toHaveLength(8);
    expect(entry(state, "p1", "doc-0")?.status).toBe("queued");

    const [afterFirst, first] = takeNextRequests(state, 1000);
    expect(first.map((r) => r.documentId)).toEqual([
      "doc-0",
      "doc-1",
      "doc-2",
      "doc-3",
      "doc-4",
    ]);
    expect(afterFirst.active).toBe(MAX_ACTIVE_REQUESTS);
    expect(entry(afterFirst, "p1", "doc-0")).toMatchObject({
      status: "running",
      startedAt: 1000,
    });
    expect(entry(afterFirst, "p1", "doc-5")?.status).toBe("queued");

    const [blocked, none] = takeNextRequests(afterFirst, 1001);
    expect(none).toEqual([]);
    expect(blocked.active).toBe(5);

    state = releaseRequest(releaseRequest(blocked));
    const [afterSecond, second] = takeNextRequests(state, 2000);
    expect(second.map((r) => r.documentId)).toEqual(["doc-5", "doc-6"]);
    expect(afterSecond.active).toBe(5);
    expect(afterSecond.queue.map((r) => r.documentId)).toEqual(["doc-7"]);
  });

  it("does not count a release below zero", () => {
    expect(releaseRequest(EMPTY_RUN_STATE).active).toBe(0);
  });

  it("replaces a prompt's settled entries when it runs again", () => {
    const first = request({ documentId: "doc-1" });
    let state = enqueueRuns(EMPTY_RUN_STATE, [first]);
    state = markRunCompleted(state, signal({ runId: first.runId }), 3, 10);
    const other = request({ promptIds: ["p2"] });
    state = enqueueRuns(state, [other]);
    state = enqueueRuns(state, [request({ documentId: "doc-2" })]);
    expect(entry(state, "p1", "doc-1")).toBeUndefined();
    expect(entry(state, "p1", "doc-2")?.status).toBe("queued");
    expect(entry(state, "p2", "doc-1")?.status).toBe("queued");
  });

  it("drops a run's entries when nothing was dispatched", () => {
    const pending = request();
    const kept = request({ documentId: "doc-2" });
    const state = removeRun(
      enqueueRuns(EMPTY_RUN_STATE, [pending, kept]),
      pending.runId,
    );
    expect(entry(state)).toBeUndefined();
    expect(entry(state, "p1", "doc-2")?.status).toBe("queued");
  });
});

describe("events", () => {
  it("starts the timer on dispatch and keeps it when the started event arrives", () => {
    const run = request();
    let [state] = takeNextRequests(enqueueRuns(EMPTY_RUN_STATE, [run]), 1000);
    state = markRunStarted(state, signal({ runId: run.runId }), 500, 1500);
    expect(entry(state)).toMatchObject({ status: "running", startedAt: 1000 });
  });

  it("resumes an unknown run from the server's start time", () => {
    const state = markRunStarted(
      EMPTY_RUN_STATE,
      signal({ runId: "other-tab" }),
      500,
      1500,
    );
    expect(entry(state)).toMatchObject({
      status: "running",
      startedAt: 500,
      runId: "other-tab",
    });
    const noTime = markRunStarted(
      EMPTY_RUN_STATE,
      signal({ runId: "x" }),
      null,
      1500,
    );
    expect(entry(noTime)?.startedAt).toBe(1500);
  });

  it("ignores a started event from an older run while a newer one is in flight", () => {
    const newer = request();
    const state = markRunStarted(
      enqueueRuns(EMPTY_RUN_STATE, [newer]),
      signal({ runId: "older" }),
      500,
      1500,
    );
    expect(entry(state)).toMatchObject({
      status: "queued",
      runId: newer.runId,
    });
  });

  it("completes the matching run with the server's elapsed time", () => {
    const run = request();
    let [state] = takeNextRequests(enqueueRuns(EMPTY_RUN_STATE, [run]), 1000);
    state = markRunCompleted(state, signal({ runId: run.runId }), 7, 8000);
    expect(entry(state)).toMatchObject({
      status: "completed",
      elapsedSeconds: 7,
      finishedAt: 8000,
    });
  });

  it("ignores a result from an older run", () => {
    const run = request();
    const state = markRunCompleted(
      enqueueRuns(EMPTY_RUN_STATE, [run]),
      signal({ runId: "older" }),
      7,
      8000,
    );
    expect(entry(state)?.status).toBe("queued");
  });

  it("accepts a result without a run id for an in-flight entry only", () => {
    const run = request();
    let state = enqueueRuns(EMPTY_RUN_STATE, [run]);
    state = markRunCompleted(state, signal(), null, 8000);
    expect(entry(state)).toMatchObject({
      status: "completed",
      elapsedSeconds: null,
    });
    const again = markRunFailed(state, signal(), failure, 9000);
    expect(entry(again)?.status).toBe("completed");
  });

  it("records the failure details, null fields included", () => {
    const run = request();
    let state = enqueueRuns(EMPTY_RUN_STATE, [run]);
    const bare: RunFailure = {
      message: "Prompt execution failed",
      provider: null,
      requestId: null,
      retryAfterSeconds: null,
    };
    state = markRunFailed(state, signal({ runId: run.runId }), bare, 9000);
    expect(entry(state)).toMatchObject({
      status: "failed",
      failure: bare,
      finishedAt: 9000,
    });
  });

  it("fails every in-flight entry of the prompts when the event names no document", () => {
    const a = request({ documentId: "doc-1" });
    const b = request({ documentId: "doc-2" });
    const other = request({ promptIds: ["p2"] });
    let state = enqueueRuns(EMPTY_RUN_STATE, [a, b, other]);
    state = markRunFailed(
      state,
      signal({ documentId: null, profileId: null }),
      failure,
      9000,
    );
    expect(entry(state, "p1", "doc-1")?.status).toBe("failed");
    expect(entry(state, "p1", "doc-2")?.status).toBe("failed");
    expect(entry(state, "p2", "doc-1")?.status).toBe("queued");
  });

  it("settles every prompt of a bulk run", () => {
    const bulk = request({ promptIds: ["p1", "p2"] });
    let state = enqueueRuns(EMPTY_RUN_STATE, [bulk]);
    state = markRunCompleted(
      state,
      signal({ runId: bulk.runId, promptIds: ["p1", "p2"] }),
      4,
      5000,
    );
    expect(entry(state, "p1")?.status).toBe("completed");
    expect(entry(state, "p2")?.status).toBe("completed");
  });
});

describe("stale runs", () => {
  it("fails only the entries still in flight for that run", () => {
    const old = request();
    let state = enqueueRuns(EMPTY_RUN_STATE, [old]);
    const newer = request();
    state = enqueueRuns(state, [newer]);
    const expiredOld = expireRun(state, old.runId, 99);
    expect(expiredOld).toBe(state);
    const expiredNew = expireRun(state, newer.runId, 99);
    expect(entry(expiredNew)).toMatchObject({
      status: "failed",
      finishedAt: 99,
      failure: { message: TIMEOUT_MESSAGE, requestId: null },
    });
  });

  it("leaves a settled entry alone", () => {
    const run = request();
    const done = markRunCompleted(
      enqueueRuns(EMPTY_RUN_STATE, [run]),
      signal({ runId: run.runId }),
      1,
      2,
    );
    expect(expireRun(done, run.runId, 99)).toBe(done);
  });

  it("lets a late result settle a timed-out run", () => {
    const run = request();
    let state = expireRun(enqueueRuns(EMPTY_RUN_STATE, [run]), run.runId, 99);
    state = markRunCompleted(state, signal({ runId: run.runId }), 900, 100);
    expect(entry(state)?.status).toBe("completed");
  });
});

describe("single pass", () => {
  it("tracks one run per tool and document", () => {
    const store = createPromptRunStore();
    store
      .getState()
      .dispatchSinglePass(
        { toolId: "tool-1", documentId: "doc-1", runId: "sp-1" },
        100,
      );
    const key = singlePassKey("tool-1", "doc-1");
    expect(store.getState().singlePass[key]).toMatchObject({
      status: "running",
      startedAt: 100,
    });
    store
      .getState()
      .started(
        signal({ runId: "sp-1", singlePass: true, promptIds: ["p1", "p2"] }),
        null,
        150,
      );
    expect(store.getState().singlePass[key]?.startedAt).toBe(100);
    store
      .getState()
      .failed(signal({ runId: "sp-1", singlePass: true }), failure, 200);
    expect(store.getState().singlePass[key]).toMatchObject({
      status: "failed",
      failure,
    });
    // Prompt entries are untouched by a single-pass event.
    expect(store.getState().entries).toEqual({});
  });

  it("ignores an older single-pass result and expires the latest only", () => {
    const store = createPromptRunStore();
    const actions = store.getState();
    actions.dispatchSinglePass(
      { toolId: "tool-1", documentId: "doc-1", runId: "sp-2" },
      1,
    );
    actions.completed(signal({ runId: "sp-1", singlePass: true }), 3, 4);
    const key = singlePassKey("tool-1", "doc-1");
    expect(store.getState().singlePass[key]?.status).toBe("running");
    expect(store.getState().expire("sp-1", 5)).toBe(false);
    expect(store.getState().expire("sp-2", 5)).toBe(true);
    expect(store.getState().singlePass[key]?.failure?.message).toBe(
      TIMEOUT_MESSAGE,
    );
    store
      .getState()
      .completed(signal({ runId: "sp-2", singlePass: true }), 3, 6);
    expect(store.getState().singlePass[key]).toMatchObject({
      status: "completed",
      elapsedSeconds: 3,
    });
  });

  it("resumes a single-pass run started elsewhere, and drops a pending one", () => {
    const store = createPromptRunStore();
    store
      .getState()
      .started(signal({ runId: "sp-9", singlePass: true }), 40, 50);
    const key = singlePassKey("tool-1", "doc-1");
    expect(store.getState().singlePass[key]?.startedAt).toBe(40);
    store.getState().drop("sp-9");
    expect(store.getState().singlePass[key]).toBeUndefined();
    store
      .getState()
      .started(
        signal({ runId: "sp-9", singlePass: true, documentId: null }),
        40,
        50,
      );
    expect(store.getState().singlePass).toEqual({});
  });

  it("holds the single-pass mode flag", () => {
    const store = createPromptRunStore();
    store.getState().setSinglePassMode(true);
    expect(store.getState().singlePassMode).toBe(true);
  });
});

describe("store actions", () => {
  it("enqueues, takes, releases and expires through the store", () => {
    const store = createPromptRunStore();
    const run = request();
    store.getState().enqueue([run]);
    expect(store.getState().take(10)).toEqual([run]);
    expect(store.getState().active).toBe(1);
    store.getState().started(signal({ runId: run.runId }), null, 11);
    expect(store.getState().expire(run.runId, 12)).toBe(true);
    expect(store.getState().expire(run.runId, 13)).toBe(false);
    store.getState().release();
    expect(store.getState().active).toBe(0);
    store.getState().drop(run.runId);
    expect(store.getState().entries).toEqual({});
  });
});
