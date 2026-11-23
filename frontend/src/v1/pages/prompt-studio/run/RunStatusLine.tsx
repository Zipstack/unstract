import { Button } from "@v1/components/ui/button";
import { InlineCode } from "@v1/components/ui/code";
import { Spinner } from "@v1/components/ui/feedback";
import { ACTION_ICONS, RAIL_ICONS, STATUS_ICONS } from "@v1/lib/icons";
import type { JSX } from "react";
import { formatClock, formatTimer, retryHint } from "./format";
import type { PromptRunSummary } from "./summary";
import { useNow } from "./useNow";

const documents = (n: number) => (n === 1 ? "document" : "documents");

export type RunStatusLineProps = Readonly<{
  summary: PromptRunSummary;
  /** Retry the prompt; left out in single pass, where per-prompt retries do not exist. */
  onRetry?: () => void;
  /** Open the run's logs in the logs console. */
  onOpenLogs?: () => void;
}>;

/** The card's run line (frames C06, C07): running with a timer, or failed with the provider's details. */
export function RunStatusLine({
  summary,
  onRetry,
  onOpenLogs,
}: RunStatusLineProps): JSX.Element | null {
  if (summary.state === "running") {
    return <RunningLine {...summary} />;
  }
  if (summary.state === "failed") {
    return (
      <FailedLine {...summary} onRetry={onRetry} onOpenLogs={onOpenLogs} />
    );
  }
  return null;
}

type RunningProps = Extract<PromptRunSummary, { state: "running" }>;

function RunningLine({
  documentCount,
  completedCount,
  startedAt,
}: RunningProps): JSX.Element {
  const now = useNow(startedAt !== null);
  return (
    <div
      data-slot="run-status"
      data-state="running"
      className="ui:flex ui:items-center ui:gap-2 ui:bg-primary-muted ui:px-3.5 ui:py-2 ui:text-body-small ui:text-primary"
    >
      <Spinner />
      <p className="ui:m-0 ui:min-w-0 ui:flex-1" aria-live="polite">
        Running on {documentCount} {documents(documentCount)} · {completedCount}{" "}
        of {documentCount} complete
      </p>
      {startedAt === null ? null : (
        <InlineCode variant="plain" aria-label="Elapsed time">
          {formatTimer(now - startedAt)}
        </InlineCode>
      )}
    </div>
  );
}

type FailedProps = Extract<PromptRunSummary, { state: "failed" }> &
  Pick<RunStatusLineProps, "onRetry" | "onOpenLogs">;

function FailedLine({
  documentCount,
  failedCount,
  failedAt,
  failure,
  onRetry,
  onOpenLogs,
}: FailedProps): JSX.Element {
  const ErrorIcon = STATUS_ICONS.error;
  const hint = retryHint(failure);
  return (
    <div data-slot="run-status" data-state="failed" role="alert">
      <div className="ui:flex ui:items-center ui:gap-2 ui:bg-muted ui:px-3.5 ui:py-2 ui:text-body-small ui:text-destructive">
        <ErrorIcon aria-hidden className="ui:size-4 ui:shrink-0" />
        <p className="ui:m-0 ui:min-w-0 ui:flex-1">
          Run failed on {failedCount} of {documentCount}{" "}
          {documents(documentCount)}
        </p>
        <InlineCode variant="plain" className="ui:text-muted-foreground">
          {formatClock(failedAt)}
        </InlineCode>
      </div>
      <div className="ui:flex ui:flex-col ui:gap-2 ui:px-3.5 ui:py-3">
        <p className="ui:m-0 ui:text-body-small ui:text-foreground">
          {failure.message}
        </p>
        {hint ? (
          <InlineCode
            variant="plain"
            className="ui:text-caption ui:text-muted-foreground"
          >
            {hint}
          </InlineCode>
        ) : null}
        {onRetry || onOpenLogs ? (
          <div className="ui:flex ui:items-center ui:gap-2">
            {onRetry ? (
              <Button
                variant="outline"
                size="sm"
                leadingIcon={ACTION_ICONS.refresh}
                onClick={onRetry}
              >
                Retry this prompt
              </Button>
            ) : null}
            {onOpenLogs ? (
              <Button
                variant="ghost"
                size="sm"
                leadingIcon={RAIL_ICONS.logs}
                onClick={onOpenLogs}
              >
                Open logs
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
