import { act, screen } from "@testing-library/react";
import { promptOutputKeys } from "@v1/services/promptOutputs";
import { RUN_RESULT_EVENT } from "@v1/services/promptRuns";
import { createPromptRunStore, runKey } from "@v1/stores/promptRuns";
import {
  apiPath,
  DEFAULT_SESSION,
  expectNoA11yViolations,
  HttpResponse,
  http,
  mockApi,
  renderHookV1,
  renderV1,
} from "@v1/test";
import {
  completedEvent,
  DOCUMENTS,
  outputRow,
  TOOL_ID,
} from "@v1/test/fixtures/promptRuns";
import type { JSX } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CellRunState,
  CoverageCaption,
  RunMetadata,
  SinglePassBanner,
} from "./captions";
import { createLocalRunChannel } from "./channel";
import { ProfilePopoverContent } from "./ProfilePopoverContent";
import {
  PromptRunProvider,
  usePromptRunActions,
  useRefreshOutputsOnReturn,
} from "./PromptRunProvider";
import { RunStatusLine } from "./RunStatusLine";

afterEach(() => {
  vi.useRealTimers();
});

const failure = {
  message:
    "Azure OpenAI returned 429 — rate limit exceeded for deployment gpt-4o (S0).",
  provider: "azure",
  requestId: "8f3a-21c9-4d10",
  retryAfterSeconds: 60,
};

describe("RunStatusLine", () => {
  it("shows the documents running and a ticking timer (C06)", async () => {
    vi.useFakeTimers({ now: 10_000 });
    renderV1(
      <RunStatusLine
        summary={{
          state: "running",
          documentCount: 4,
          completedCount: 2,
          startedAt: 3_000,
        }}
      />,
    );
    expect(
      screen.getByText("Running on 4 documents · 2 of 4 complete"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Elapsed time")).toHaveTextContent("00:07");
    await act(() => vi.advanceTimersByTimeAsync(2_000));
    expect(screen.getByLabelText("Elapsed time")).toHaveTextContent("00:09");
  });

  it("shows no timer while every request is still queued", () => {
    renderV1(
      <RunStatusLine
        summary={{
          state: "running",
          documentCount: 1,
          completedCount: 0,
          startedAt: null,
        }}
      />,
    );
    expect(
      screen.getByText("Running on 1 document · 0 of 1 complete"),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Elapsed time")).toBeNull();
  });

  it("shows the failure, its request id and retry hint, and the actions (C07)", async () => {
    const onRetry = vi.fn();
    const onOpenLogs = vi.fn();
    const failedAt = new Date(2026, 10, 24, 14, 6, 22).getTime();
    const { user, container } = renderV1(
      <RunStatusLine
        summary={{
          state: "failed",
          documentCount: 4,
          failedCount: 2,
          failedAt,
          failure,
        }}
        onRetry={onRetry}
        onOpenLogs={onOpenLogs}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Run failed on 2 of 4 documents",
    );
    expect(screen.getByText("14:06:22")).toBeInTheDocument();
    expect(screen.getByText(failure.message)).toBeInTheDocument();
    expect(
      screen.getByText("request_id: 8f3a-21c9-4d10 · retry after 60s"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry this prompt" }));
    await user.click(screen.getByRole("button", { name: "Open logs" }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(onOpenLogs).toHaveBeenCalledOnce();
    await expectNoA11yViolations(container);
  });

  it("leaves out the hint and the actions it has no data or handler for", () => {
    renderV1(
      <RunStatusLine
        summary={{
          state: "failed",
          documentCount: 1,
          failedCount: 1,
          failedAt: 0,
          failure: {
            ...failure,
            requestId: null,
            retryAfterSeconds: null,
          },
        }}
      />,
    );
    expect(screen.queryByText(/request_id/)).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders nothing when idle or complete", () => {
    const { container, rerender } = renderV1(
      <RunStatusLine summary={{ state: "idle" }} />,
    );
    expect(container.querySelector("[data-slot=run-status]")).toBeNull();
    rerender(
      <RunStatusLine summary={{ state: "completed", documentCount: 2 }} />,
    );
    expect(container.querySelector("[data-slot=run-status]")).toBeNull();
  });
});

describe("captions", () => {
  it("names the documents a prompt has not run on, and opens coverage", async () => {
    const onOpen = vi.fn();
    const { user } = renderV1(
      <CoverageCaption
        coverage={{ covered: 3, total: 4, missing: [DOCUMENTS[3]] }}
        onOpen={onOpen}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Coverage: 3 of 4 docs" }),
    );
    expect(onOpen).toHaveBeenCalledOnce();
    expect(
      screen.getByText("· Not run on statement-apr.pdf"),
    ).toBeInTheDocument();
  });

  it("shows full coverage as plain text without a handler (C11)", () => {
    renderV1(
      <CoverageCaption coverage={{ covered: 4, total: 4, missing: [] }} />,
    );
    expect(screen.getByText("Coverage: 4 of 4 docs")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByText(/Not run on/)).toBeNull();
  });

  it("explains single pass extraction (C11)", async () => {
    const { container } = renderV1(<SinglePassBanner />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Single pass extraction is on",
    );
    expect(
      screen.getByText(/All prompts are sent to the model in one request/),
    ).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("shows tokens, time and cost, NA when unknown", () => {
    const { rerender } = renderV1(
      <RunMetadata tokens={10_014} seconds={1.8} cost={0.02507} />,
    );
    expect(screen.getByText("Tokens: 10,014")).toBeInTheDocument();
    expect(screen.getByText("Time: 1.8s")).toBeInTheDocument();
    expect(screen.getByText("Cost: $0.02507")).toBeInTheDocument();
    rerender(<RunMetadata tokens={null} seconds={null} cost={null} />);
    expect(screen.getByText("Tokens: NA")).toBeInTheDocument();
    expect(screen.getByText("Time: 0s")).toBeInTheDocument();
    expect(screen.getByText("Cost: NA")).toBeInTheDocument();
  });

  it("shows a cell running or yet to run", () => {
    const { rerender } = renderV1(<CellRunState status="running" />);
    expect(screen.getByText("Running…")).toBeInTheDocument();
    rerender(<CellRunState status="idle" />);
    expect(screen.getByText("Yet to run")).toBeInTheDocument();
  });
});

describe("ProfilePopoverContent", () => {
  it("lists the profile behind a model column (C13)", async () => {
    const { container } = renderV1(
      <ProfilePopoverContent
        profile={{
          name: "test3",
          llm: "claude-sonnet-4-6",
          embeddingModel: "az-embed-ada-002",
          vectorDatabase: "postgres neon db",
          textExtractor: "LLM Whisperer V2",
          chunkSize: 0,
          reindex: false,
        }}
      />,
    );
    expect(screen.getByRole("region", { name: "test3" })).toBeInTheDocument();
    expect(
      screen.getByText("LLM profile used by this model column"),
    ).toBeInTheDocument();
    const terms = screen.getAllByRole("term").map((t) => t.textContent);
    expect(terms).toEqual([
      "LLM",
      "Embedding Model",
      "Vector Database",
      "Text Extractor",
      "Chunk size",
      "Reindex",
    ]);
    const values = screen.getAllByRole("definition").map((d) => d.textContent);
    expect(values).toEqual([
      "claude-sonnet-4-6",
      "az-embed-ada-002",
      "postgres neon db",
      "LLM Whisperer V2",
      "0",
      "No",
    ]);
    await expectNoA11yViolations(container);
  });
});

describe("PromptRunProvider", () => {
  function RunButton(): JSX.Element {
    const actions = usePromptRunActions();
    return (
      <button
        type="button"
        disabled={!actions}
        onClick={() =>
          actions?.run({
            toolId: TOOL_ID,
            promptIds: ["p1"],
            profileIds: ["profile-1"],
            documentIds: ["doc-1"],
          })
        }
      >
        Run
      </button>
    );
  }

  it("runs a prompt and lands its result from the channel", async () => {
    const store = createPromptRunStore();
    const channel = createLocalRunChannel();
    let runId = "";
    mockApi(
      http.post(
        apiPath(DEFAULT_SESSION, `/prompt-studio/fetch_response/${TOOL_ID}`),
        async ({ request }) => {
          runId = ((await request.json()) as { run_id: string }).run_id;
          return HttpResponse.json(
            { task_id: "t", run_id: runId, status: "accepted" },
            { status: 202 },
          );
        },
      ),
    );
    const { user, queryClient } = renderV1(
      <PromptRunProvider channel={channel} store={store}>
        <RunButton />
      </PromptRunProvider>,
    );
    const list = { toolId: TOOL_ID, documentId: "doc-1" };
    queryClient.setQueryData(promptOutputKeys.list(list), []);
    await user.click(await screen.findByRole("button", { name: "Run" }));
    await vi.waitFor(() => expect(runId).not.toBe(""));
    const key = runKey("p1", "doc-1", "profile-1");
    expect(store.getState().entries[key]?.status).toBe("running");
    act(() =>
      channel.emit(
        RUN_RESULT_EVENT,
        completedEvent({ run_id: runId, outputs: [outputRow()] }),
      ),
    );
    expect(store.getState().entries[key]?.status).toBe("completed");
    expect(queryClient.getQueryData(promptOutputKeys.list(list))).toHaveLength(
      1,
    );
  });

  it("refetches the tool's outputs when the workspace mounts during a run", () => {
    const store = createPromptRunStore();
    const idle = renderHookV1(() => useRefreshOutputsOnReturn(TOOL_ID, store));
    const list = { toolId: TOOL_ID };
    idle.queryClient.setQueryData(promptOutputKeys.list(list), []);
    idle.unmount();
    expect(
      idle.queryClient.getQueryState(promptOutputKeys.list(list))
        ?.isInvalidated,
    ).toBe(false);

    store.getState().enqueue([
      {
        runId: "r",
        toolId: TOOL_ID,
        documentId: "doc-1",
        profileId: "profile-1",
        promptIds: ["p1"],
      },
    ]);
    renderHookV1(() => useRefreshOutputsOnReturn(TOOL_ID, store), {
      queryClient: idle.queryClient,
    });
    expect(
      idle.queryClient.getQueryState(promptOutputKeys.list(list))
        ?.isInvalidated,
    ).toBe(true);
  });
});
