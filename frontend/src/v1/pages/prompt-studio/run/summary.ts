import {
  isInFlight,
  type RunEntry,
  type RunFailure,
  type RunState,
  type RunStatus,
  runKey,
} from "@v1/stores/promptRuns";

/*
 * What a prompt card says about its latest run, from the run state. Counts
 * are per document: a document is complete when every profile it ran under
 * completed, and failed when any did.
 */

export type PromptRunSummary =
  | Readonly<{ state: "idle" }>
  | Readonly<{
      state: "running";
      documentCount: number;
      completedCount: number;
      /** Earliest start among the requests already sent; null while all are queued. */
      startedAt: number | null;
    }>
  | Readonly<{
      state: "failed";
      documentCount: number;
      failedCount: number;
      failedAt: number;
      /** The most recent failure. */
      failure: RunFailure;
    }>
  | Readonly<{ state: "completed"; documentCount: number }>;

export function summarizePromptRun(
  entries: Readonly<Record<string, RunEntry>>,
  promptId: string,
): PromptRunSummary {
  const mine = Object.values(entries).filter((e) => e.promptId === promptId);
  if (mine.length === 0) {
    return { state: "idle" };
  }
  const byDocument = new Map<string, RunEntry[]>();
  for (const e of mine) {
    byDocument.set(e.documentId, [...(byDocument.get(e.documentId) ?? []), e]);
  }
  const documents = [...byDocument.values()];
  const documentCount = documents.length;
  const inFlight = mine.filter((e) => isInFlight(e.status));
  if (inFlight.length > 0) {
    const starts = inFlight.flatMap((e) =>
      e.startedAt === null ? [] : [e.startedAt],
    );
    return {
      state: "running",
      documentCount,
      completedCount: documents.filter((d) =>
        d.every((e) => e.status === "completed"),
      ).length,
      startedAt: starts.length > 0 ? Math.min(...starts) : null,
    };
  }
  const failed = mine
    .filter((e) => e.status === "failed" && e.failure)
    .sort((a, b) => (b.finishedAt ?? 0) - (a.finishedAt ?? 0));
  const latest = failed[0];
  if (latest?.failure) {
    return {
      state: "failed",
      documentCount,
      failedCount: documents.filter((d) => d.some((e) => e.status === "failed"))
        .length,
      failedAt: latest.finishedAt ?? 0,
      failure: latest.failure,
    };
  }
  return { state: "completed", documentCount };
}

/** One model-grid cell's status; idle when it never ran in this page load. */
export function cellRunStatus(
  entries: Readonly<Record<string, RunEntry>>,
  promptId: string,
  documentId: string,
  profileId: string,
): RunStatus | "idle" {
  return entries[runKey(promptId, documentId, profileId)]?.status ?? "idle";
}

/** Anything queued or running for the tool: the workspace locks its run controls. */
export function isToolRunning(state: RunState, toolId: string): boolean {
  return (
    Object.values(state.entries).some(
      (e) => e.toolId === toolId && isInFlight(e.status),
    ) ||
    Object.values(state.singlePass).some(
      (r) => r.toolId === toolId && isInFlight(r.status),
    )
  );
}
