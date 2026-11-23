import type { PromptOutput } from "@v1/services/promptOutputs";

/* Prompt Studio run fixtures: output rows and run events as the backend sends them. */

export const TOOL_ID = "tool-1";
export const PROFILE_ID = "profile-1";
export const DOCUMENTS = [
  { documentId: "doc-1", documentName: "statement-jan.pdf" },
  { documentId: "doc-2", documentName: "statement-feb.pdf" },
  { documentId: "doc-3", documentName: "statement-mar.pdf" },
  { documentId: "doc-4", documentName: "statement-apr.pdf" },
] as const;

/** An output row as `GET prompt-output/` serialises it. */
export function outputRow(overrides: Partial<PromptOutput> = {}): PromptOutput {
  return {
    prompt_output_id: `out-${overrides.prompt_id ?? "p1"}-${overrides.document_manager ?? "doc-1"}`,
    prompt_id: "p1",
    document_manager: "doc-1",
    profile_manager: PROFILE_ID,
    tool_id: TOOL_ID,
    run_id: "run-1",
    output: "Bank of America",
    is_single_pass_extract: false,
    context: ["…"],
    highlight_data: null,
    token_usage: {
      embedding_tokens: 0,
      prompt_tokens: 10_000,
      completion_tokens: 14,
      total_tokens: 10_014,
      cost_in_dollars: 0.02507,
    },
    coverage: ["doc-1"],
    ...overrides,
  };
}

type EventOverrides = Readonly<Record<string, unknown>>;

/** `prompt_studio_run_started`, wrapped as the socket sends it. */
export function startedEvent(overrides: EventOverrides = {}): unknown {
  return {
    data: {
      task_id: "task-1",
      operation: "fetch_response",
      tool_id: TOOL_ID,
      status: "started",
      run_id: "run-1",
      prompt_ids: ["p1"],
      document_id: "doc-1",
      profile_manager_id: PROFILE_ID,
      started_at: "2026-11-24T09:15:02.481233+00:00",
      ...overrides,
    },
  };
}

/** `prompt_studio_result` with `status: "completed"`. */
export function completedEvent(overrides: EventOverrides = {}): unknown {
  return {
    data: {
      task_id: "task-1",
      operation: "fetch_response",
      tool_id: TOOL_ID,
      status: "completed",
      run_id: "run-1",
      prompt_ids: ["p1"],
      document_id: "doc-1",
      profile_manager_id: PROFILE_ID,
      elapsed: 7,
      outputs: null,
      ...overrides,
    },
  };
}

/** `prompt_studio_result` with `status: "failed"`: the C07 rate limit. */
export function failedEvent(overrides: EventOverrides = {}): unknown {
  return {
    data: {
      task_id: "task-1",
      operation: "fetch_response",
      tool_id: TOOL_ID,
      status: "failed",
      run_id: "run-1",
      prompt_ids: ["p1"],
      document_id: "doc-1",
      profile_manager_id: PROFILE_ID,
      error:
        "Error from LLM adapter 'gpt-4o (azure)': RateLimitError (HTTP 429): Rate limit exceeded",
      error_details: {
        provider: "azure",
        request_id: "8f3a-21c9-4d10",
        retry_after_seconds: 60,
      },
      ...overrides,
    },
  };
}
