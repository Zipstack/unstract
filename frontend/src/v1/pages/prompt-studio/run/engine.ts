import type { QueryClient } from "@tanstack/react-query";
import { notify as defaultNotify, type NotifyInput } from "@v1/lib/notify";
import { newUuid } from "@v1/lib/uuid";
import { toApiError } from "@v1/services/errors";
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
  type RunFailure,
  type RunPlan,
  type RunRequest,
  type RunSignal,
  type RunStore,
  TIMEOUT_MESSAGE,
} from "@v1/stores/promptRuns";
import type { RunChannel } from "./channel";

/*
 * The run engine: sends queued requests (five at a time, oldest first),
 * times out stale runs, and turns socket events into run state and output
 * cache updates. One engine per provider mount; the provider sits above the
 * workspace, so a run keeps going when the user leaves the project.
 */

/** v0's stale-run limit: a run with no result after this is treated as lost. One LLM adapter call defaults to 900 s. */
export const STALE_RUN_MS = 16 * 60 * 1000;
/** How often the stale-run check looks at the runs in flight. */
const STALE_CHECK_MS = 5_000;
export const PENDING_MESSAGE = "Document is being indexed. Please wait.";
const COMPLETED_MESSAGE = "Prompt execution completed successfully.";
const SINGLE_PASS_COMPLETED_MESSAGE =
  "Single pass extraction completed successfully.";
const FAILED_MESSAGE = "Prompt run failed.";
const SINGLE_PASS_FAILED_MESSAGE = "Single pass extraction failed.";

// Toast ids, so a burst of results replaces one toast instead of stacking;
// a success never replaces a failure.
const COMPLETED_TOAST_ID = "prompt-run-completed";
const FAILED_TOAST_ID = "prompt-run-failed";
const TIMEOUT_TOAST_ID = "prompt-run-timeout";
const PENDING_TOAST_ID = "prompt-run-pending";

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
  /** Stops listening and stops the stale-run check. */
  dispose: () => void;
}>;

const OUTPUT_RESOURCE = "prompt-outputs";

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
 * belong in, or a refetch when the event could not carry them or a list
 * fetch is in flight (it would overwrite the merge with older rows).
 */
export function applyRunOutputs(
  queryClient: QueryClient,
  toolId: string,
  rows: readonly PromptOutput[] | null | undefined,
): void {
  const queries = queryClient
    .getQueryCache()
    .findAll({ predicate: isToolOutputList(toolId) });
  if (!rows || queries.some((q) => q.state.fetchStatus !== "idle")) {
    void refreshToolOutputs(queryClient, toolId);
    return;
  }
  for (const { queryKey } of queries) {
    const params = outputListParams(queryKey);
    const data = queryClient.getQueryData<PromptOutput[]>(queryKey);
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
    // The error callback may send an empty run id: treat it as missing.
    runId: event.run_id || null,
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
  newRunId = newUuid,
  notify = defaultNotify,
  report = (error) => reportApiError(error),
}: RunEngineDeps): RunEngine {
  const state = () => store.getState();

  // Age is read from the store, so this also times out runs resumed from
  // another tab or left by an earlier engine.
  const expireStale = () => {
    const toolIds = state().expireStale(Date.now(), STALE_RUN_MS);
    if (toolIds.length === 0) {
      return;
    }
    notify({ kind: "warning", title: TIMEOUT_MESSAGE, id: TIMEOUT_TOAST_ID });
    for (const toolId of toolIds) {
      void refreshToolOutputs(queryClient, toolId);
    }
  };
  const staleCheck = setInterval(expireStale, STALE_CHECK_MS);

  /** Accepted: wait for the socket. Pending: nothing was dispatched. */
  const onResponse = (runId: string, response: RunResponse) => {
    if (response.status === "pending") {
      state().drop(runId);
      notify({
        kind: "info",
        title: response.message || PENDING_MESSAGE,
        id: PENDING_TOAST_ID,
      });
    }
  };

  const onRequestError = (runId: string, error: unknown) => {
    const { message, requestId } = toApiError(error);
    const failure: RunFailure = {
      message,
      provider: null,
      requestId: requestId ?? null,
      retryAfterSeconds: null,
    };
    state().fail(runId, failure, Date.now());
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
    const signal = toSignal(event);
    if (event.status === "completed") {
      state().completed(signal, event.elapsed ?? null, Date.now());
      applyRunOutputs(queryClient, event.tool_id, event.outputs);
      notify({
        kind: "success",
        title: signal.singlePass
          ? SINGLE_PASS_COMPLETED_MESSAGE
          : COMPLETED_MESSAGE,
        id: COMPLETED_TOAST_ID,
      });
      return;
    }
    const details = toErrorDetails(event);
    const message =
      event.error ||
      (signal.singlePass ? SINGLE_PASS_FAILED_MESSAGE : FAILED_MESSAGE);
    state().failed(signal, { message, ...details }, Date.now());
    notify({
      kind: "error",
      title: message,
      requestId: details.requestId ?? undefined,
      id: FAILED_TOAST_ID,
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
        .then((response) => onResponse(runId, response))
        .catch((error: unknown) => onRequestError(runId, error));
    },
    dispose: () => {
      for (const stop of unsubscribe) {
        stop();
      }
      clearInterval(staleCheck);
    },
  };
}
