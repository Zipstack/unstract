import {
  apiPath,
  DEFAULT_SESSION,
  HttpResponse,
  http,
  mockApi,
} from "@v1/test";
import {
  completedEvent,
  failedEvent,
  outputRow,
  startedEvent,
  TOOL_ID,
} from "@v1/test/fixtures/promptRuns";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { setOrganizationId } from "./context";
import {
  listPromptOutputs,
  matchesOutputParams,
  mergePromptOutputs,
  promptOutputKeys,
  promptOutputQueries,
  promptOutputSchema,
} from "./promptOutputs";
import {
  parseRunResult,
  parseRunStarted,
  runPrompt,
  runPrompts,
  runSinglePass,
  toErrorDetails,
} from "./promptRuns";

beforeEach(() => setOrganizationId(DEFAULT_SESSION.organization.id));
afterEach(() => setOrganizationId(null));

it("parses the wrapped started event", () => {
  expect(parseRunStarted(startedEvent())).toMatchObject({
    status: "started",
    run_id: "run-1",
    prompt_ids: ["p1"],
    started_at: "2026-11-24T09:15:02.481233+00:00",
  });
});

it("parses a bare started event, and rejects a result event as one", () => {
  const bare = (startedEvent() as { data: unknown }).data;
  expect(parseRunStarted(bare)?.task_id).toBe("task-1");
  expect(parseRunStarted(completedEvent())).toBeNull();
});

it("parses a completed event with null outputs as a refetch signal", () => {
  const event = parseRunResult(completedEvent());
  expect(event?.status).toBe("completed");
  expect(event?.status === "completed" && event.outputs).toBeNull();
});

it("parses inline outputs with the row schema", () => {
  const event = parseRunResult(completedEvent({ outputs: [outputRow()] }));
  expect(event?.status === "completed" && event.outputs?.[0]?.output).toBe(
    "Bank of America",
  );
});

it("maps failure details, null fields included", () => {
  const event = parseRunResult(failedEvent());
  expect(event?.status === "failed" && toErrorDetails(event)).toEqual({
    provider: "azure",
    requestId: "8f3a-21c9-4d10",
    retryAfterSeconds: 60,
  });
  const crashed = parseRunResult(
    failedEvent({
      error_details: {
        provider: null,
        request_id: null,
        retry_after_seconds: null,
      },
    }),
  );
  expect(crashed?.status === "failed" && toErrorDetails(crashed)).toEqual({
    provider: null,
    requestId: null,
    retryAfterSeconds: null,
  });
  const legacy = parseRunResult(failedEvent({ error_details: undefined }));
  expect(legacy?.status === "failed" && toErrorDetails(legacy)).toEqual({
    provider: null,
    requestId: null,
    retryAfterSeconds: null,
  });
});

it("ignores index_document events and malformed payloads", () => {
  expect(
    parseRunResult(completedEvent({ operation: "index_document" })),
  ).toBeNull();
  expect(parseRunResult({ data: { status: "completed" } })).toBeNull();
  expect(parseRunResult(null)).toBeNull();
});

it("coerces a string cost and an empty coverage object", () => {
  const row = promptOutputSchema.parse({
    ...outputRow(),
    token_usage: { total_tokens: 12, cost_in_dollars: "0.00010" },
    coverage: {},
  });
  expect(row.token_usage.cost_in_dollars).toBe(0.0001);
  expect(row.token_usage.prompt_tokens).toBeNull();
  expect(row.coverage).toEqual([]);
  const empty = promptOutputSchema.parse({
    ...outputRow(),
    token_usage: { cost_in_dollars: "n/a" },
  });
  expect(empty.token_usage.cost_in_dollars).toBeNull();
});

it("posts one prompt run with the client's run id", async () => {
  let body: unknown;
  mockApi(
    http.post(
      apiPath(DEFAULT_SESSION, `/prompt-studio/fetch_response/${TOOL_ID}`),
      async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { task_id: "task-1", run_id: "run-1", status: "accepted" },
          { status: 202 },
        );
      },
    ),
  );
  const response = await runPrompt({
    toolId: TOOL_ID,
    promptId: "p1",
    documentId: "doc-1",
    profileId: "profile-1",
    runId: "run-1",
  });
  expect(response).toEqual({
    task_id: "task-1",
    run_id: "run-1",
    status: "accepted",
  });
  expect(body).toEqual({
    id: "p1",
    document_id: "doc-1",
    profile_manager: "profile-1",
    run_id: "run-1",
  });
});

it("posts a bulk run and reads the pending-indexing answer", async () => {
  let body: unknown;
  mockApi(
    http.post(
      apiPath(DEFAULT_SESSION, `/prompt-studio/bulk_fetch_response/${TOOL_ID}`),
      async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { status: "pending", message: "Document is being indexed" },
          { status: 202 },
        );
      },
    ),
  );
  const response = await runPrompts({
    toolId: TOOL_ID,
    promptIds: ["p1", "p2"],
    documentId: "doc-1",
    profileId: "profile-1",
    runId: "run-2",
  });
  expect(response).toEqual({
    status: "pending",
    message: "Document is being indexed",
  });
  expect(body).toMatchObject({ prompt_ids: ["p1", "p2"], run_id: "run-2" });
});

it("posts single pass and reads the accepted answer", async () => {
  let body: unknown;
  mockApi(
    http.post(
      apiPath(
        DEFAULT_SESSION,
        `/prompt-studio/single-pass-extraction/${TOOL_ID}`,
      ),
      async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { status: "accepted", task_id: "t-3", run_id: "run-3" },
          { status: 202 },
        );
      },
    ),
  );
  const response = await runSinglePass({
    toolId: TOOL_ID,
    documentId: "doc-1",
    runId: "run-3",
  });
  expect(body).toEqual({ document_id: "doc-1", run_id: "run-3" });
  expect(response).toEqual({
    status: "accepted",
    task_id: "t-3",
    run_id: "run-3",
  });
});

it("rejects a synchronous list of rows as a single-pass answer", async () => {
  mockApi(
    http.post(
      apiPath(
        DEFAULT_SESSION,
        `/prompt-studio/single-pass-extraction/${TOOL_ID}`,
      ),
      () => HttpResponse.json([outputRow({ is_single_pass_extract: true })]),
    ),
  );
  await expect(
    runSinglePass({ toolId: TOOL_ID, documentId: "doc-1", runId: "run-3" }),
  ).rejects.toThrow();
});

it("lists outputs with only the filters given", async () => {
  const seen: URL[] = [];
  mockApi(
    http.get(
      apiPath(DEFAULT_SESSION, "/prompt-studio/prompt-output/"),
      ({ request }) => {
        seen.push(new URL(request.url));
        return HttpResponse.json([outputRow()]);
      },
    ),
  );
  const rows = await listPromptOutputs({
    toolId: TOOL_ID,
    documentId: "doc-1",
    singlePass: false,
  });
  expect(rows).toHaveLength(1);
  expect(Object.fromEntries(seen[0]?.searchParams ?? [])).toEqual({
    tool_id: TOOL_ID,
    document_manager: "doc-1",
    is_single_pass_extract: "false",
  });
});

it("keys outputs by organisation and params", () => {
  const params = { toolId: TOOL_ID, documentId: "doc-1" };
  expect(promptOutputKeys.list(params)).toEqual([
    "org-1",
    "prompt-outputs",
    "list",
    params,
  ]);
  expect(promptOutputQueries.list(params).queryKey).toEqual(
    promptOutputKeys.list(params),
  );
});

it("merges incoming rows by slot and skips rows the list excludes", () => {
  const old = outputRow({ output: "old" });
  const other = outputRow({ prompt_id: "p2", output: "kept" });
  const fresh = outputRow({ output: "new" });
  const elsewhere = outputRow({ document_manager: "doc-2" });
  const merged = mergePromptOutputs([old, other], [fresh, elsewhere], {
    toolId: TOOL_ID,
    documentId: "doc-1",
  });
  expect(merged.map((row) => row.output)).toEqual(["kept", "new"]);
  expect(
    matchesOutputParams(outputRow(), {
      toolId: TOOL_ID,
      promptId: "p2",
    }),
  ).toBe(false);
  expect(
    matchesOutputParams(outputRow(), {
      toolId: TOOL_ID,
      profileId: "other",
    }),
  ).toBe(false);
  expect(
    matchesOutputParams(outputRow(), { toolId: TOOL_ID, singlePass: true }),
  ).toBe(false);
});

it("keeps rows of other documents, profiles and modes in an unfiltered list", () => {
  const params = { toolId: TOOL_ID, singlePass: false };
  const current = [outputRow({ output: "doc-1" })];
  const merged = mergePromptOutputs(
    current,
    [
      outputRow({ document_manager: "doc-2", output: "doc-2" }),
      outputRow({ profile_manager: "profile-2", output: "profile-2" }),
    ],
    params,
  );
  expect(merged.map((row) => row.output)).toEqual([
    "doc-1",
    "doc-2",
    "profile-2",
  ]);
  expect(
    mergePromptOutputs(current, [outputRow({ output: "new" })], params).map(
      (row) => row.output,
    ),
  ).toEqual(["new"]);
});

it("reads a list without a mode as the server does: not single pass", () => {
  const params = { toolId: TOOL_ID };
  expect(
    matchesOutputParams(outputRow({ is_single_pass_extract: true }), params),
  ).toBe(false);
  expect(matchesOutputParams(outputRow(), params)).toBe(true);
});

it("keeps a result event whose outputs or failure details do not match", () => {
  const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
  const completed = parseRunResult(
    completedEvent({ outputs: [{ output: 5 }] }),
  );
  expect(completed).toMatchObject({ status: "completed", outputs: null });
  const failed = parseRunResult(
    failedEvent({ error_details: { request_id: 42 } }),
  );
  expect(failed).toMatchObject({ status: "failed", error_details: null });
  const fractional = parseRunResult(
    failedEvent({ error_details: { retry_after_seconds: 1.5 } }),
  );
  expect(fractional?.status === "failed" && fractional.error_details).toEqual({
    retry_after_seconds: 1.5,
  });
  expect(error).not.toHaveBeenCalled();
});

it("logs a run event it cannot read, and stays quiet for other operations", () => {
  const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
  expect(parseRunResult(completedEvent({ tool_id: 7 }))).toBeNull();
  expect(parseRunStarted(startedEvent({ task_id: null }))).toBeNull();
  expect(error).toHaveBeenCalledTimes(2);
  error.mockClear();
  expect(
    parseRunResult(completedEvent({ operation: "index_document" })),
  ).toBeNull();
  expect(parseRunResult(null)).toBeNull();
  expect(error).not.toHaveBeenCalled();
});
