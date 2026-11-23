import { z } from "zod";
import { http, orgPath, type RequestOptions } from "./http";
import { promptOutputListSchema } from "./promptOutputs";

/*
 * Prompt Studio runs: the calls that start them and the socket events that
 * report them (`prompt_studio_run_started`, and `prompt_studio_result` with
 * `run_id`, inline `outputs` and `error_details`). A POST only dispatches the
 * run; the result arrives on the socket.
 */

export const RUN_STARTED_EVENT = "prompt_studio_run_started";
export const RUN_RESULT_EVENT = "prompt_studio_result";
export type RunEventName = typeof RUN_STARTED_EVENT | typeof RUN_RESULT_EVENT;

export const RUN_OPERATIONS = [
  "fetch_response",
  "single_pass_extraction",
] as const;
export type RunOperation = (typeof RUN_OPERATIONS)[number];

const runOperation = z.enum(RUN_OPERATIONS);

// Fields every run event carries. `run_id` is optional so an event from a
// backend without the new fields still parses.
const runEventBase = {
  task_id: z.string(),
  operation: runOperation,
  tool_id: z.string(),
  run_id: z.string().nullish(),
  prompt_ids: z.array(z.string()).default([]),
  document_id: z.string().nullish(),
  profile_manager_id: z.string().nullish(),
};

export const runStartedEventSchema = z.object({
  ...runEventBase,
  status: z.literal("started"),
  /** Dispatch time (ISO 8601, UTC); only for resuming a timer after a reload. */
  started_at: z.string().nullish(),
});
export type RunStartedEvent = z.infer<typeof runStartedEventSchema>;

export const runCompletedEventSchema = z.object({
  ...runEventBase,
  status: z.literal("completed"),
  /** Whole seconds from dispatch, queue wait included. */
  elapsed: z.number().nullish(),
  /** The persisted rows; null (or absent) means refetch `prompt-output/`. */
  outputs: promptOutputListSchema.nullish(),
});
export type RunCompletedEvent = z.infer<typeof runCompletedEventSchema>;

export const errorDetailsSchema = z.object({
  provider: z.string().nullish(),
  request_id: z.string().nullish(),
  retry_after_seconds: z.number().int().nullish(),
});
export type ErrorDetails = Readonly<{
  provider: string | null;
  requestId: string | null;
  retryAfterSeconds: number | null;
}>;

export const runFailedEventSchema = z.object({
  ...runEventBase,
  status: z.literal("failed"),
  error: z.string().nullish(),
  error_details: errorDetailsSchema.nullish(),
});
export type RunFailedEvent = z.infer<typeof runFailedEventSchema>;

const runResultEventSchema = z.discriminatedUnion("status", [
  runCompletedEventSchema,
  runFailedEventSchema,
]);
export type RunResultEvent = z.infer<typeof runResultEventSchema>;

/** The events arrive wrapped as `{ data: payload }`; older senders send it bare. */
function unwrap(payload: unknown): unknown {
  if (
    payload !== null &&
    typeof payload === "object" &&
    "data" in payload &&
    !("status" in payload)
  ) {
    return payload.data;
  }
  return payload;
}

/** A started event, or null when the payload is not one. */
export function parseRunStarted(payload: unknown): RunStartedEvent | null {
  const parsed = runStartedEventSchema.safeParse(unwrap(payload));
  return parsed.success ? parsed.data : null;
}

/**
 * A prompt run's result event, or null for anything else on that event name
 * (`index_document` belongs to the documents pane) or a payload that does
 * not match.
 */
export function parseRunResult(payload: unknown): RunResultEvent | null {
  const parsed = runResultEventSchema.safeParse(unwrap(payload));
  return parsed.success ? parsed.data : null;
}

/** The failure details with every field present; null fields when unknown. */
export function toErrorDetails(event: RunFailedEvent): ErrorDetails {
  const details = event.error_details;
  return {
    provider: details?.provider ?? null,
    requestId: details?.request_id ?? null,
    retryAfterSeconds: details?.retry_after_seconds ?? null,
  };
}

/** What a run POST answers with. */
const acceptedSchema = z.object({
  status: z.literal("accepted"),
  task_id: z.string(),
  run_id: z.string(),
});
/** The document is still being indexed: nothing was dispatched. */
const pendingSchema = z.object({
  status: z.literal("pending"),
  message: z.string().nullish(),
});
const runResponseSchema = z.discriminatedUnion("status", [
  acceptedSchema,
  pendingSchema,
]);
export type RunResponse = z.infer<typeof runResponseSchema>;

// An old synchronous single-pass backend answers 200 with the rows.
const singlePassResponseSchema = z.union([
  runResponseSchema,
  promptOutputListSchema,
]);
export type SinglePassResponse = z.infer<typeof singlePassResponseSchema>;

export type PromptRunRequest = Readonly<{
  toolId: string;
  promptId: string;
  documentId: string;
  profileId: string;
  runId: string;
}>;

export type BulkPromptRunRequest = Readonly<{
  toolId: string;
  promptIds: readonly string[];
  documentId: string;
  profileId: string;
  runId: string;
}>;

export type SinglePassRequest = Readonly<{
  toolId: string;
  documentId: string;
  runId: string;
}>;

const toolPath = (action: string, toolId: string) =>
  `/prompt-studio/${action}/${encodeURIComponent(toolId)}` as const;

/** `POST prompt-studio/fetch_response/<tool>`: one prompt on one document and profile. */
export async function runPrompt(
  request: PromptRunRequest,
  { signal, org }: RequestOptions = {},
): Promise<RunResponse> {
  const { data } = await http.post<unknown>(
    orgPath(toolPath("fetch_response", request.toolId), org),
    {
      id: request.promptId,
      document_id: request.documentId,
      profile_manager: request.profileId,
      run_id: request.runId,
    },
    { signal },
  );
  return runResponseSchema.parse(data);
}

/** `POST prompt-studio/bulk_fetch_response/<tool>`: several prompts in one task. */
export async function runPrompts(
  request: BulkPromptRunRequest,
  { signal, org }: RequestOptions = {},
): Promise<RunResponse> {
  const { data } = await http.post<unknown>(
    orgPath(toolPath("bulk_fetch_response", request.toolId), org),
    {
      prompt_ids: request.promptIds,
      document_id: request.documentId,
      profile_manager: request.profileId,
      run_id: request.runId,
    },
    { signal },
  );
  return runResponseSchema.parse(data);
}

/** `POST prompt-studio/single-pass-extraction/<tool>`: every eligible prompt in one request. */
export async function runSinglePass(
  request: SinglePassRequest,
  { signal, org }: RequestOptions = {},
): Promise<SinglePassResponse> {
  const { data } = await http.post<unknown>(
    orgPath(toolPath("single-pass-extraction", request.toolId), org),
    { document_id: request.documentId, run_id: request.runId },
    { signal },
  );
  return singlePassResponseSchema.parse(data);
}
