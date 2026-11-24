import { useStore } from "zustand";
import { createStore, type StoreApi } from "zustand/vanilla";

/*
 * Prompt Studio run state: the request queue and the status of every
 * prompt x document x profile a run touches. The reducers are pure and
 * exported for tests; the store wraps them. Nothing here calls the backend:
 * the run engine (pages/prompt-studio/run) sends the requests and feeds the
 * socket events in as `RunSignal`s.
 *
 * The state lives for the page load, so a run keeps its status when the user
 * leaves the workspace and comes back.
 */

/** In-flight POSTs at once, as in v0. */
export const MAX_ACTIVE_REQUESTS = 5;
export const TIMEOUT_MESSAGE = "Prompt execution timed out. Please try again.";

export type RunStatus = "queued" | "running" | "completed" | "failed";

export type RunFailure = Readonly<{
  /** The backend's message, shown as is. */
  message: string;
  provider: string | null;
  requestId: string | null;
  retryAfterSeconds: number | null;
}>;

/** One prompt on one document under one profile. */
export type RunEntry = Readonly<{
  toolId: string;
  promptId: string;
  documentId: string;
  profileId: string;
  /** The `run_id` sent with the request; events and late results are matched on it. */
  runId: string;
  status: RunStatus;
  /** Client clock (ms) when the request went out, or the server's start on resume. */
  startedAt: number | null;
  finishedAt: number | null;
  elapsedSeconds: number | null;
  failure: RunFailure | null;
}>;

/** One POST: a single prompt (`fetch_response`) or several (`bulk_fetch_response`). */
export type RunRequest = Readonly<{
  runId: string;
  toolId: string;
  documentId: string;
  profileId: string;
  promptIds: readonly string[];
}>;

/** A single-pass run of one document; per-prompt status does not exist for it. */
export type SinglePassRun = Readonly<{
  toolId: string;
  documentId: string;
  runId: string;
  status: RunStatus;
  startedAt: number | null;
  finishedAt: number | null;
  elapsedSeconds: number | null;
  failure: RunFailure | null;
}>;

/** A socket event, reduced to what the state needs. */
export type RunSignal = Readonly<{
  toolId: string;
  /** Null from a backend that does not send it. */
  runId: string | null;
  promptIds: readonly string[];
  documentId: string | null;
  profileId: string | null;
  singlePass: boolean;
}>;

export type RunState = Readonly<{
  entries: Readonly<Record<string, RunEntry>>;
  queue: readonly RunRequest[];
  /** Requests sent and not yet answered. */
  active: number;
  singlePass: Readonly<Record<string, SinglePassRun>>;
  singlePassMode: boolean;
}>;

export const EMPTY_RUN_STATE: RunState = {
  entries: {},
  queue: [],
  active: 0,
  singlePass: {},
  singlePassMode: false,
};

export const runKey = (
  promptId: string,
  documentId: string,
  profileId: string,
): string => `${promptId}__${documentId}__${profileId}`;

export const singlePassKey = (toolId: string, documentId: string): string =>
  `${toolId}__${documentId}`;

export const isInFlight = (status: RunStatus): boolean =>
  status === "queued" || status === "running";

export type RunPlan = Readonly<{
  toolId: string;
  promptIds: readonly string[];
  profileIds: readonly string[];
  documentIds: readonly string[];
  newRunId: () => string;
}>;

/**
 * The requests for a run, in v0's order (profile, then document). One prompt
 * gets a request per profile and document; several share one bulk request
 * per profile and document, so an unindexed document is indexed once.
 */
export function planRun(plan: RunPlan): RunRequest[] {
  const groups =
    plan.promptIds.length > 1
      ? [plan.promptIds]
      : plan.promptIds.map((id) => [id]);
  return groups.flatMap((promptIds) =>
    plan.profileIds.flatMap((profileId) =>
      plan.documentIds.map((documentId) => ({
        runId: plan.newRunId(),
        toolId: plan.toolId,
        documentId,
        profileId,
        promptIds,
      })),
    ),
  );
}

function withEntries(
  state: RunState,
  entries: Record<string, RunEntry>,
): RunState {
  return { ...state, entries };
}

/** Queues requests; a prompt that runs again loses its settled entries, so its summary is this run's. */
export function enqueueRuns(
  state: RunState,
  requests: readonly RunRequest[],
): RunState {
  const prompts = new Set(requests.flatMap((r) => r.promptIds));
  const kept = Object.fromEntries(
    Object.entries(state.entries).filter(
      ([, e]) => isInFlight(e.status) || !prompts.has(e.promptId),
    ),
  );
  const queued = Object.fromEntries(
    requests.flatMap((r) =>
      r.promptIds.map((promptId): [string, RunEntry] => [
        runKey(promptId, r.documentId, r.profileId),
        {
          toolId: r.toolId,
          promptId,
          documentId: r.documentId,
          profileId: r.profileId,
          runId: r.runId,
          status: "queued",
          startedAt: null,
          finishedAt: null,
          elapsedSeconds: null,
          failure: null,
        },
      ]),
    ),
  );
  return {
    ...state,
    entries: { ...kept, ...queued },
    queue: [...state.queue, ...requests],
  };
}

/** Takes the requests that fit under the cap, oldest first, and marks them running. */
export function takeNextRequests(
  state: RunState,
  now: number,
): [RunState, RunRequest[]] {
  const room = Math.max(0, MAX_ACTIVE_REQUESTS - state.active);
  const taken = state.queue.slice(0, room);
  if (taken.length === 0) {
    return [state, []];
  }
  const runIds = new Set(taken.map((r) => r.runId));
  const entries = Object.fromEntries(
    Object.entries(state.entries).map(([key, e]) => [
      key,
      runIds.has(e.runId) && e.status === "queued"
        ? { ...e, status: "running" as const, startedAt: now }
        : e,
    ]),
  );
  return [
    {
      ...state,
      entries,
      queue: state.queue.slice(taken.length),
      active: state.active + taken.length,
    },
    taken,
  ];
}

/** A request was answered (accepted, pending or failed): its slot is free. */
export function releaseRequest(state: RunState): RunState {
  return { ...state, active: Math.max(0, state.active - 1) };
}

/** Nothing was dispatched for this run (the document is still indexing). */
export function removeRun(state: RunState, runId: string): RunState {
  const entries = Object.fromEntries(
    Object.entries(state.entries).filter(([, e]) => e.runId !== runId),
  );
  const singlePass = Object.fromEntries(
    Object.entries(state.singlePass).filter(([, r]) => r.runId !== runId),
  );
  return { ...state, entries, singlePass };
}

/** Does this event settle an entry: the same run, or any in-flight one when the event has no run id. */
function settles(
  e: Pick<RunEntry, "runId" | "status">,
  signal: RunSignal,
): boolean {
  return signal.runId === null
    ? isInFlight(e.status)
    : e.runId === signal.runId;
}

/** The keys an event names; null when it names no document or profile. */
function signalKeys(signal: RunSignal): string[] | null {
  const { documentId, profileId } = signal;
  if (!documentId || !profileId) {
    return null;
  }
  return signal.promptIds.map((p) => runKey(p, documentId, profileId));
}

type Settle = (e: RunEntry) => RunEntry;

function settleEntries(
  state: RunState,
  signal: RunSignal,
  settle: Settle,
): RunState {
  const keys = signalKeys(signal);
  const prompts = new Set(signal.promptIds);
  const targets =
    keys ??
    Object.keys(state.entries).filter((key) => {
      const e = state.entries[key];
      return e && e.toolId === signal.toolId && prompts.has(e.promptId);
    });
  let changed = false;
  const entries = { ...state.entries };
  for (const key of targets) {
    const e = entries[key];
    if (e && settles(e, signal)) {
      entries[key] = settle(e);
      changed = true;
    }
  }
  return changed ? withEntries(state, entries) : state;
}

function updateSinglePass(
  state: RunState,
  signal: RunSignal,
  update: (run: SinglePassRun | undefined) => SinglePassRun | undefined,
): RunState {
  if (!signal.documentId) {
    return state;
  }
  const key = singlePassKey(signal.toolId, signal.documentId);
  const next = update(state.singlePass[key]);
  if (!next) {
    return state;
  }
  return { ...state, singlePass: { ...state.singlePass, [key]: next } };
}

/** The run was dispatched; `serverStartedAt` is the start only for a run this page did not start. */
export function markRunStarted(
  state: RunState,
  signal: RunSignal,
  serverStartedAt: number | null,
  now: number,
): RunState {
  const begin = <T extends RunEntry | SinglePassRun>(
    current: T | undefined,
    fresh: T,
  ): T | undefined => {
    if (!current) {
      return fresh;
    }
    const sameRun = current.runId === signal.runId;
    if (!isInFlight(current.status)) {
      // Started can trail the result of a run that failed at once: ignore it.
      return sameRun ? undefined : fresh;
    }
    if (signal.runId !== null && !sameRun) {
      return undefined; // An older run of the same slot.
    }
    return {
      ...current,
      status: "running",
      startedAt: current.startedAt ?? now,
    };
  };
  const base = {
    toolId: signal.toolId,
    runId: signal.runId ?? "",
    status: "running" as const,
    startedAt: serverStartedAt ?? now,
    finishedAt: null,
    elapsedSeconds: null,
    failure: null,
  };
  if (signal.singlePass) {
    return updateSinglePass(state, signal, (run) =>
      begin(run, { ...base, documentId: signal.documentId ?? "" }),
    );
  }
  const { documentId, profileId } = signal;
  if (!documentId || !profileId) {
    return state;
  }
  const entries = { ...state.entries };
  let changed = false;
  for (const promptId of signal.promptIds) {
    const key = runKey(promptId, documentId, profileId);
    const next = begin(entries[key], {
      ...base,
      promptId,
      documentId,
      profileId,
    });
    if (next) {
      entries[key] = next;
      changed = true;
    }
  }
  return changed ? withEntries(state, entries) : state;
}

function settleRun(
  state: RunState,
  signal: RunSignal,
  settle: <T extends RunEntry | SinglePassRun>(e: T) => T,
): RunState {
  if (signal.singlePass) {
    return updateSinglePass(state, signal, (run) =>
      run && settles(run, signal) ? settle(run) : undefined,
    );
  }
  return settleEntries(state, signal, settle);
}

export function markRunCompleted(
  state: RunState,
  signal: RunSignal,
  elapsedSeconds: number | null,
  now: number,
): RunState {
  return settleRun(state, signal, (e) => ({
    ...e,
    status: "completed",
    finishedAt: now,
    elapsedSeconds,
    failure: null,
  }));
}

export function markRunFailed(
  state: RunState,
  signal: RunSignal,
  failure: RunFailure,
  now: number,
): RunState {
  return settleRun(state, signal, (e) => ({
    ...e,
    status: "failed",
    finishedAt: now,
    failure,
  }));
}

/** Fails the entries of one run still in flight; the same state when none is. */
export function failRun(
  state: RunState,
  runId: string,
  failure: RunFailure,
  now: number,
): RunState {
  return failWhere(state, (e) => e.runId === runId, failure, now)[0];
}

const TIMEOUT_FAILURE: RunFailure = {
  message: TIMEOUT_MESSAGE,
  provider: null,
  requestId: null,
  retryAfterSeconds: null,
};

/**
 * The stale-run guard: fails every request sent at least `maxAgeMs` ago that
 * has no result, and names the tools it touched. Age is read from the state,
 * so a run resumed from another tab, or left by an earlier engine, expires
 * too; a newer run of the same slot is younger and is left alone.
 */
export function expireStaleRuns(
  state: RunState,
  now: number,
  maxAgeMs: number,
): [RunState, string[]] {
  return failWhere(
    state,
    (e) => e.startedAt !== null && now - e.startedAt >= maxAgeMs,
    TIMEOUT_FAILURE,
    now,
  );
}

type Flight = Pick<RunEntry, "runId" | "startedAt">;

function failWhere(
  state: RunState,
  matches: (e: Flight) => boolean,
  failure: RunFailure,
  now: number,
): [RunState, string[]] {
  const toolIds = new Set<string>();
  const fail = <T extends RunEntry | SinglePassRun>(e: T): T => {
    if (!isInFlight(e.status) || !matches(e)) {
      return e;
    }
    toolIds.add(e.toolId);
    return { ...e, status: "failed", finishedAt: now, failure };
  };
  const mapAll = <T extends RunEntry | SinglePassRun>(
    record: Readonly<Record<string, T>>,
  ): Record<string, T> =>
    Object.fromEntries(Object.entries(record).map(([k, e]) => [k, fail(e)]));
  const entries = mapAll(state.entries);
  const singlePass = mapAll(state.singlePass);
  return toolIds.size === 0
    ? [state, []]
    : [{ ...state, entries, singlePass }, [...toolIds]];
}

export type RunActions = Readonly<{
  enqueue: (requests: readonly RunRequest[]) => void;
  /** Takes the requests that fit under the cap; the caller sends them. */
  take: (now: number) => RunRequest[];
  release: () => void;
  drop: (runId: string) => void;
  dispatchSinglePass: (
    run: Readonly<{ toolId: string; documentId: string; runId: string }>,
    now: number,
  ) => void;
  started: (
    signal: RunSignal,
    serverStartedAt: number | null,
    now: number,
  ) => void;
  completed: (
    signal: RunSignal,
    elapsedSeconds: number | null,
    now: number,
  ) => void;
  failed: (signal: RunSignal, failure: RunFailure, now: number) => void;
  /** A run's request failed: its entries still in flight fail with it. */
  fail: (runId: string, failure: RunFailure, now: number) => void;
  /** Times out the stale runs; returns the tools they belong to. */
  expireStale: (now: number, maxAgeMs: number) => string[];
  setSinglePassMode: (on: boolean) => void;
}>;

export type RunStore = StoreApi<RunState & RunActions>;

/** A run store; the app uses one (`promptRunStore`), tests make their own. */
export function createPromptRunStore(): RunStore {
  return createStore<RunState & RunActions>()((set, get) => ({
    ...EMPTY_RUN_STATE,
    enqueue: (requests) => set((s) => enqueueRuns(s, requests)),
    take: (now) => {
      const [next, taken] = takeNextRequests(get(), now);
      set(next);
      return taken;
    },
    release: () => set((s) => releaseRequest(s)),
    drop: (runId) => set((s) => removeRun(s, runId)),
    dispatchSinglePass: ({ toolId, documentId, runId }, now) =>
      set((s) => ({
        singlePass: {
          ...s.singlePass,
          [singlePassKey(toolId, documentId)]: {
            toolId,
            documentId,
            runId,
            status: "running",
            startedAt: now,
            finishedAt: null,
            elapsedSeconds: null,
            failure: null,
          },
        },
      })),
    started: (signal, serverStartedAt, now) =>
      set((s) => markRunStarted(s, signal, serverStartedAt, now)),
    completed: (signal, elapsed, now) =>
      set((s) => markRunCompleted(s, signal, elapsed, now)),
    failed: (signal, failure, now) =>
      set((s) => markRunFailed(s, signal, failure, now)),
    fail: (runId, failure, now) => set((s) => failRun(s, runId, failure, now)),
    expireStale: (now, maxAgeMs) => {
      const [next, toolIds] = expireStaleRuns(get(), now, maxAgeMs);
      if (toolIds.length > 0) {
        set(next);
      }
      return toolIds;
    },
    setSinglePassMode: (on) => set({ singlePassMode: on }),
  }));
}

/** The page load's run store. */
export const promptRunStore: RunStore = createPromptRunStore();

/** Reads the run store through a selector. */
export function usePromptRunStore<T>(
  selector: (state: RunState & RunActions) => T,
): T {
  return useStore(promptRunStore, selector);
}
