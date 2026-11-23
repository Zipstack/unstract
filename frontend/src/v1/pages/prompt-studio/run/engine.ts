import type { QueryClient } from "@tanstack/react-query";
import { notify as defaultNotify, type NotifyInput } from "@v1/lib/notify";
import {
  mergePromptOutputs,
  type PromptOutput,
  type PromptOutputParams,
} from "@v1/services/promptOutputs";
import {
  parseRunResult,
  parseRunStarted,
  RUN_RESULT_EVENT,
  RUN_STARTED_EVENT,
  type RunResponse,
  type RunResultEvent,
  type RunStartedEvent,
  runPrompt,
  runPrompts,
  runSinglePass,
  toErrorDetails,
} from "@v1/services/promptRuns";
import { reportApiError } from "@v1/services/report";
import {
  planRun,
  type RunPlan,
  type RunRequest,
  type RunSignal,
  type RunStore,
  TIMEOUT_MESSAGE,
} from "@v1/stores/promptRuns";
import type { RunChannel } from "./channel";

/*
 * The run engine: sends queued requests (five at a time, oldest first),
 * arms the stale-run timer per run, and turns socket events into run state
 * and output cache updates. One engine runs per page load, mounted above the
 * workspace, so a run keeps going when the user leaves the project.
 */

/** Longer than the LLM adapter's 900 s default, so the UI never gives up first. */
export const STALE_RUN_MS = 16 * 60 * 1000;
export const PENDING_MESSAGE = "Document is being indexed. Please wait.";
const COMPLETED_MESSAGE = "Prompt execution completed successfully.";
const SINGLE_PASS_COMPLETED_MESSAGE =
  "Single pass extraction completed successfully.";

// Toast ids, so a burst of results replaces one toast instead of stacking.
const RESULT_TOAST_ID = "prompt-run-result";
const TIMEOUT_TOAST_ID = "prompt-run-timeout";

export type RunClient = Readonly<{
  runPrompt: typeof runPrompt;
  runPrompts: typeof runPrompts;
  runSinglePass: typeof runSinglePass;
}>;

export type RunEngineDeps = Readonly<{
  store: RunStore;
  channel: RunChannel;
  queryClient: QueryClient;
  client?: RunClient;
  newRunId?: () => string;
  notify?: (input: NotifyInput) => void;
  report?: (error: unknown) => void;
}>;

export type RunEngine = Readonly<{
  /** Queues every prompt x profile x document of the plan. */
  run: (plan: Omit<RunPlan, "newRunId">) => void;
  /** One request for every eligible prompt of the tool on one document. */
  runSinglePass: (
    target: Readonly<{ toolId: string; documentId: string }>,
  ) => void;
  /** Stops listening and cancels the stale-run timers. */
  dispose: () => void;
}>;

const OUTPUT_RESOURCE = "promptOutputs";

/** The params of a cached output list, or null for any other query. */
function outputListParams(
  queryKey: readonly unknown[],
): PromptOutputParams | null {
  return queryKey[1] === OUTPUT_RESOURCE && queryKey[2] === "list"
    ? (queryKey[3] as PromptOutputParams)
    : null;
}

const isToolOutputList =
  (toolId: string) =>
  ({ queryKey }: { queryKey: readonly unknown[] }) =>
    outputListParams(queryKey)?.toolId === toolId;

/** Refetches every output list of a tool that is on screen, and marks the rest stale. */
export function refreshToolOutputs(
  queryClient: QueryClient,
  toolId: string,
): Promise<void> {
  return queryClient.invalidateQueries({ predicate: isToolOutputList(toolId) });
}

/**
 * Applies a run's outputs: merged into every cached list of the tool they
 * belong in, or, when the event could not carry them, a refetch.
 */
export function applyRunOutputs(
  queryClient: QueryClient,
  toolId: string,
  rows: readonly PromptOutput[] | null | undefined,
): void {
  if (!rows) {
    void refreshToolOutputs(queryClient, toolId);
    return;
  }
  for (const [queryKey, data] of queryClient.getQueriesData<PromptOutput[]>({
    predicate: isToolOutputList(toolId),
  })) {
    const params = outputListParams(queryKey);
    if (params && data) {
      queryClient.setQueryData(
        queryKey,
        mergePromptOutputs(data, rows, params),
      );
    }
  }
}

function toSignal(event: RunStartedEvent | RunResultEvent): RunSignal {
  return {
    toolId: event.tool_id,
    runId: event.run_id ?? null,
    promptIds: event.prompt_ids,
    documentId: event.document_id ?? null,
    profileId: event.profile_manager_id ?? null,
    singlePass: event.operation === "single_pass_extraction",
  };
}

function parseTime(value: string | null | undefined): number | null {
  const time = value ? Date.parse(value) : Number.NaN;
  return Number.isNaN(time) ? null : time;
}

export function createRunEngine({
  store,
  channel,
  queryClient,
  client = { runPrompt, runPrompts, runSinglePass },
  newRunId = () => crypto.randomUUID(),
  notify = defaultNotify,
  report = (error) => reportApiError(error),
}: RunEngineDeps): RunEngine {
  const timers = new Map<string, ReturnType<typeof setTimeout>>();
  const state = () => store.getState();

  const clearTimer = (runId: string | null | undefined) => {
    const timer = runId ? timers.get(runId) : undefined;
    if (runId && timer !== undefined) {
      clearTimeout(timer);
      timers.delete(runId);
    }
  };

  const armTimer = (runId: string) => {
    clearTimer(runId);
    timers.set(
      runId,
      setTimeout(() => {
        timers.delete(runId);
        if (state().expire(runId, Date.now())) {
          notify({
            kind: "warning",
            title: TIMEOUT_MESSAGE,
            id: TIMEOUT_TOAST_ID,
          });
        }
      }, STALE_RUN_MS),
    );
  };

  /** Accepted: wait for the socket. Pending: nothing was dispatched. */
  const onResponse = (runId: string, response: RunResponse) => {
    if (response.status === "pending") {
      state().drop(runId);
      notify({ kind: "info", title: response.message || PENDING_MESSAGE });
      return;
    }
    armTimer(runId);
  };

  const onRequestError = (runId: string, error: unknown) => {
    state().drop(runId);
    report(error);
  };

  const send = (request: RunRequest) => {
    const [promptId] = request.promptIds;
    const call =
      request.promptIds.length > 1 || promptId === undefined
        ? client.runPrompts(request)
        : client.runPrompt({ ...request, promptId });
    call
      .then((response) => onResponse(request.runId, response))
      .catch((error: unknown) => onRequestError(request.runId, error))
      .finally(() => {
        state().release();
        drain();
      });
  };

  const drain = () => {
    for (const request of state().take(Date.now())) {
      send(request);
    }
  };

  // Payloads arrive raw, so any transport can hand them over; parsed here.
  const onStarted = (payload: unknown) => {
    const event = parseRunStarted(payload);
    if (event) {
      state().started(toSignal(event), parseTime(event.started_at), Date.now());
    }
  };

  const onResult = (payload: unknown) => {
    const event = parseRunResult(payload);
    if (!event) {
      return;
    }
    clearTimer(event.run_id);
    const signal = toSignal(event);
    if (event.status === "completed") {
      state().completed(signal, event.elapsed ?? null, Date.now());
      applyRunOutputs(queryClient, event.tool_id, event.outputs);
      notify({
        kind: "success",
        title: signal.singlePass
          ? SINGLE_PASS_COMPLETED_MESSAGE
          : COMPLETED_MESSAGE,
        id: RESULT_TOAST_ID,
      });
      return;
    }
    const details = toErrorDetails(event);
    const message = event.error || `${event.operation} failed`;
    state().failed(signal, { message, ...details }, Date.now());
    notify({
      kind: "error",
      title: message,
      requestId: details.requestId ?? undefined,
      id: RESULT_TOAST_ID,
    });
  };

  const unsubscribe = [
    channel.subscribe(RUN_STARTED_EVENT, onStarted),
    channel.subscribe(RUN_RESULT_EVENT, onResult),
  ];

  return {
    run: (plan) => {
      const requests = planRun({ ...plan, newRunId });
      if (requests.length > 0) {
        state().enqueue(requests);
        drain();
      }
    },
    runSinglePass: ({ toolId, documentId }) => {
      const runId = newRunId();
      state().dispatchSinglePass({ toolId, documentId, runId }, Date.now());
      client
        .runSinglePass({ toolId, documentId, runId })
        .then((response) => {
          if (Array.isArray(response)) {
            const signal: RunSignal = {
              toolId,
              runId,
              promptIds: [],
              documentId,
              profileId: null,
              singlePass: true,
            };
            state().completed(signal, null, Date.now());
            applyRunOutputs(queryClient, toolId, response);
            return;
          }
          onResponse(runId, response);
        })
        .catch((error: unknown) => onRequestError(runId, error));
    },
    dispose: () => {
      for (const stop of unsubscribe) {
        stop();
      }
      for (const timer of timers.values()) {
        clearTimeout(timer);
      }
      timers.clear();
    },
  };
}
