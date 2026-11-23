import {
  createPromptRunStore,
  type RunEntry,
  type RunFailure,
  runKey,
} from "@v1/stores/promptRuns";
import { DOCUMENTS, outputRow } from "@v1/test/fixtures/promptRuns";
import { describe, expect, it } from "vitest";
import { computeCoverage, describeMissing } from "./coverage";
import {
  formatClock,
  formatCost,
  formatSeconds,
  formatTimer,
  formatTokens,
  retryHint,
} from "./format";
import { cellRunStatus, isToolRunning, summarizePromptRun } from "./summary";

const failure: RunFailure = {
  message: "Rate limit exceeded",
  provider: "azure",
  requestId: "8f3a-21c9-4d10",
  retryAfterSeconds: 60,
};

function entries(...items: Partial<RunEntry>[]): Record<string, RunEntry> {
  return Object.fromEntries(
    items.map((item) => {
      const e: RunEntry = {
        toolId: "tool-1",
        promptId: "p1",
        documentId: "doc-1",
        profileId: "profile-1",
        runId: "run-1",
        status: "running",
        startedAt: null,
        finishedAt: null,
        elapsedSeconds: null,
        failure: null,
        ...item,
      };
      return [runKey(e.promptId, e.documentId, e.profileId), e];
    }),
  );
}

describe("coverage", () => {
  const documents = DOCUMENTS;

  it("counts the documents each prompt has an output for, and names the rest", () => {
    const rows = [
      outputRow({ document_manager: "doc-1" }),
      outputRow({ document_manager: "doc-2" }),
      outputRow({ document_manager: "doc-3" }),
      outputRow({ prompt_id: "p2", document_manager: "doc-1" }),
    ];
    const coverage = computeCoverage({
      prompts: [{ promptId: "p1" }, { promptId: "p2" }],
      documents,
      rows,
      singlePass: false,
    });
    expect(coverage.byPrompt.p1).toMatchObject({ covered: 3, total: 4 });
    expect(coverage.byPrompt.p1?.missing.map((d) => d.documentName)).toEqual([
      "statement-apr.pdf",
    ]);
    expect(coverage.byPrompt.p2?.covered).toBe(1);
    expect(coverage.complete).toBe(false);
    expect(coverage.missingCount).toBe(4);
  });

  it("is complete only when every prompt covers every document", () => {
    const rows = documents.map((d) =>
      outputRow({ document_manager: d.documentId }),
    );
    const coverage = computeCoverage({
      prompts: [{ promptId: "p1" }],
      documents,
      rows,
      singlePass: false,
    });
    expect(coverage.complete).toBe(true);
    expect(coverage.byPrompt.p1?.missing).toEqual([]);
  });

  it("counts only the mode and the profile asked for", () => {
    const rows = [
      outputRow({ document_manager: "doc-1", is_single_pass_extract: true }),
      outputRow({ document_manager: "doc-2", profile_manager: "other" }),
      outputRow({ document_manager: "doc-3" }),
    ];
    const multi = computeCoverage({
      prompts: [{ promptId: "p1", profileId: "profile-1" }],
      documents,
      rows,
      singlePass: false,
    });
    expect(multi.byPrompt.p1?.covered).toBe(1);
    const anyProfile = computeCoverage({
      prompts: [{ promptId: "p1" }],
      documents,
      rows,
      singlePass: false,
    });
    expect(anyProfile.byPrompt.p1?.covered).toBe(2);
    const single = computeCoverage({
      prompts: [{ promptId: "p1" }],
      documents,
      rows,
      singlePass: true,
    });
    expect(single.byPrompt.p1?.covered).toBe(1);
  });

  it("ignores rows for documents no longer in the project", () => {
    const coverage = computeCoverage({
      prompts: [{ promptId: "p1" }],
      documents: documents.slice(0, 1),
      rows: [outputRow({ document_manager: "deleted" })],
      singlePass: false,
    });
    expect(coverage.byPrompt.p1).toMatchObject({ covered: 0, total: 1 });
  });

  it("names up to two missing documents, then a count", () => {
    expect(describeMissing([])).toBe("");
    expect(describeMissing(documents.slice(0, 1))).toBe("statement-jan.pdf");
    expect(describeMissing(documents.slice(0, 2))).toBe(
      "statement-jan.pdf and statement-feb.pdf",
    );
    expect(describeMissing(documents)).toBe(
      "statement-jan.pdf, statement-feb.pdf and 2 more",
    );
  });
});

describe("summary", () => {
  it("is idle with no entries for the prompt", () => {
    expect(summarizePromptRun(entries({ promptId: "p2" }), "p1")).toEqual({
      state: "idle",
    });
  });

  it("counts documents running and complete, and times from the earliest start", () => {
    const summary = summarizePromptRun(
      entries(
        { documentId: "doc-1", status: "completed", startedAt: 100 },
        { documentId: "doc-2", status: "completed", startedAt: 50 },
        { documentId: "doc-3", status: "running", startedAt: 300 },
        { documentId: "doc-4", status: "queued" },
        {
          documentId: "doc-4",
          profileId: "profile-2",
          status: "running",
          startedAt: 200,
        },
      ),
      "p1",
    );
    expect(summary).toEqual({
      state: "running",
      documentCount: 4,
      completedCount: 2,
      startedAt: 200,
    });
  });

  it("has no start while everything is queued", () => {
    expect(
      summarizePromptRun(entries({ status: "queued" }), "p1"),
    ).toMatchObject({
      state: "running",
      startedAt: null,
    });
  });

  it("counts a document complete only when every profile completed", () => {
    const summary = summarizePromptRun(
      entries(
        { status: "completed" },
        { profileId: "profile-2", status: "running", startedAt: 1 },
      ),
      "p1",
    );
    expect(summary).toMatchObject({ completedCount: 0, documentCount: 1 });
  });

  it("reports the latest failure once nothing is in flight", () => {
    const summary = summarizePromptRun(
      entries(
        { documentId: "doc-1", status: "completed" },
        { documentId: "doc-2", status: "completed" },
        {
          documentId: "doc-3",
          status: "failed",
          finishedAt: 10,
          failure: { ...failure, message: "older" },
        },
        { documentId: "doc-4", status: "failed", finishedAt: 20, failure },
      ),
      "p1",
    );
    expect(summary).toEqual({
      state: "failed",
      documentCount: 4,
      failedCount: 2,
      failedAt: 20,
      failure,
    });
  });

  it("is complete when every document completed", () => {
    expect(
      summarizePromptRun(
        entries({ status: "completed", elapsedSeconds: 3 }),
        "p1",
      ),
    ).toEqual({ state: "completed", documentCount: 1 });
  });

  it("reads one cell's status, idle when it never ran", () => {
    const all = entries({ status: "failed", failure });
    expect(cellRunStatus(all, "p1", "doc-1", "profile-1")).toBe("failed");
    expect(cellRunStatus(all, "p1", "doc-2", "profile-1")).toBe("idle");
  });

  it("says whether a tool has anything in flight, single pass included", () => {
    const store = createPromptRunStore();
    expect(isToolRunning(store.getState(), "tool-1")).toBe(false);
    store.getState().enqueue([
      {
        runId: "r",
        toolId: "tool-1",
        documentId: "d",
        profileId: "p",
        promptIds: ["x"],
      },
    ]);
    expect(isToolRunning(store.getState(), "tool-1")).toBe(true);
    expect(isToolRunning(store.getState(), "tool-2")).toBe(false);
    store
      .getState()
      .dispatchSinglePass({ toolId: "tool-2", documentId: "d", runId: "s" }, 1);
    expect(isToolRunning(store.getState(), "tool-2")).toBe(true);
  });
});

describe("format", () => {
  it("formats the running timer as minutes and seconds", () => {
    expect(formatTimer(7_400)).toBe("00:07");
    expect(formatTimer(-5)).toBe("00:00");
    expect(formatTimer(61 * 60 * 1000 + 5_000)).toBe("1:01:05");
  });

  it("formats the failure time of day", () => {
    const at = new Date(2026, 10, 24, 14, 6, 22).getTime();
    expect(formatClock(at)).toBe("14:06:22");
  });

  it("formats tokens, cost and time as v0 does, NA when unknown", () => {
    expect(formatTokens(10_014)).toBe("10,014");
    expect(formatTokens(null)).toBe("NA");
    expect(formatCost(0.02507)).toBe("$0.02507");
    expect(formatCost(1234.5)).toBe("$1,234.50000");
    expect(formatCost(null)).toBe("NA");
    expect(formatSeconds(1.84)).toBe("1.8s");
    expect(formatSeconds(7)).toBe("7s");
    expect(formatSeconds(null)).toBe("0s");
  });

  it("joins the request id and retry hint that are known", () => {
    expect(retryHint({ requestId: "8f3a", retryAfterSeconds: 60 })).toBe(
      "request_id: 8f3a · retry after 60s",
    );
    expect(retryHint({ requestId: null, retryAfterSeconds: 5 })).toBe(
      "retry after 5s",
    );
    expect(retryHint({ requestId: null, retryAfterSeconds: null })).toBe("");
  });
});
