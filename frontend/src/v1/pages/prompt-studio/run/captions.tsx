import { Button } from "@v1/components/ui/button";
import { InlineCode } from "@v1/components/ui/code";
import { Spinner } from "@v1/components/ui/feedback";
import { cn } from "@v1/lib/cn";
import { SHELL_ICONS, STATUS_ICONS } from "@v1/lib/icons";
import type { RunStatus } from "@v1/stores/promptRuns";
import type { JSX } from "react";
import { describeMissing, type PromptCoverage } from "./coverage";
import { formatCost, formatSeconds, formatTokens } from "./format";

/* The small run captions a prompt card hosts (frames C06, C07, C11). */

export type CoverageCaptionProps = Readonly<{
  coverage: PromptCoverage;
  /** Opens the per-document coverage view; plain text without it. */
  onOpen?: () => void;
}>;

/** "Coverage: 3 of 4 docs · Not run on statement-apr.pdf". */
export function CoverageCaption({
  coverage,
  onOpen,
}: CoverageCaptionProps): JSX.Element {
  const SearchIcon = SHELL_ICONS.search;
  // C06 draws a prompt that covers nothing in the warning colour.
  const tone =
    coverage.covered === 0 && coverage.total > 0
      ? "ui:text-warning"
      : "ui:text-primary";
  const label = `Coverage: ${coverage.covered} of ${coverage.total} docs`;
  const missing = describeMissing(coverage.missing);
  const body = (
    <>
      <SearchIcon aria-hidden className="ui:size-3.5 ui:shrink-0" />
      <span>{label}</span>
    </>
  );
  return (
    <p
      data-slot="coverage-caption"
      className="ui:m-0 ui:flex ui:min-w-0 ui:items-center ui:gap-1.5 ui:text-caption ui:font-medium"
    >
      {onOpen ? (
        <Button
          variant="link"
          size="xs"
          leadingIcon={SearchIcon}
          onClick={onOpen}
          className={cn("ui:h-auto ui:gap-1.5 ui:px-0", tone)}
        >
          {label}
        </Button>
      ) : (
        <span className={cn("ui:inline-flex ui:items-center ui:gap-1.5", tone)}>
          {body}
        </span>
      )}
      {missing ? (
        <span className="ui:truncate ui:text-muted-foreground">
          · Not run on {missing}
        </span>
      ) : null}
    </p>
  );
}

/** Frame C11's banner while single pass extraction is on. */
export function SinglePassBanner(): JSX.Element {
  const InfoIcon = STATUS_ICONS.info;
  return (
    <div
      data-slot="single-pass-banner"
      className="ui:flex ui:items-start ui:gap-2.5 ui:rounded-lg ui:bg-primary-muted ui:px-3.5 ui:py-3"
    >
      <InfoIcon
        aria-hidden
        className="ui:mt-0.5 ui:size-4 ui:shrink-0 ui:text-primary"
      />
      <div className="ui:flex ui:min-w-0 ui:flex-col ui:gap-0.5">
        <p className="ui:m-0 ui:text-body-small ui:leading-5 ui:font-semibold ui:text-primary">
          Single pass extraction is on
        </p>
        <p className="ui:m-0 ui:text-caption ui:text-foreground">
          All prompts are sent to the model in one request. Cost drops, but
          per-prompt timing and per-prompt retries are no longer available.
        </p>
      </div>
    </div>
  );
}

export type RunMetadataProps = Readonly<{
  /** Total tokens of the run that wrote the output; null shows NA. */
  tokens: number | null;
  /** Server-measured seconds; null shows 0s. */
  seconds: number | null;
  /** Dollars; null shows NA. */
  cost: number | null;
  className?: string;
}>;

/** "Tokens: 10,014  Time: 1.8s  Cost: $0.02507" under a model column. */
export function RunMetadata({
  tokens,
  seconds,
  cost,
  className,
}: RunMetadataProps): JSX.Element {
  return (
    <p
      data-slot="run-metadata"
      className={cn(
        "ui:m-0 ui:flex ui:flex-wrap ui:gap-x-2.5 ui:text-caption ui:text-muted-foreground",
        className,
      )}
    >
      <InlineCode variant="plain" className="ui:text-caption">
        Tokens: {formatTokens(tokens)}
      </InlineCode>
      <InlineCode variant="plain" className="ui:text-caption">
        Time: {formatSeconds(seconds)}
      </InlineCode>
      <InlineCode variant="plain" className="ui:text-caption">
        Cost: {formatCost(cost)}
      </InlineCode>
    </p>
  );
}

export type CellRunStateProps = Readonly<{
  /** The cell's status from `cellRunStatus`; a completed cell shows its output instead. */
  status: RunStatus | "idle";
}>;

const CELL_LINE =
  "ui:m-0 ui:flex ui:items-center ui:gap-1.5 ui:text-caption ui:font-medium";

/** A model-grid cell with no output to show: "Running…", "Run failed" or "Yet to run". */
export function CellRunState({
  status,
}: CellRunStateProps): JSX.Element | null {
  if (status === "completed") {
    return null;
  }
  if (status === "queued" || status === "running") {
    return (
      <p className={cn(CELL_LINE, "ui:text-muted-foreground")}>
        <Spinner />
        Running…
      </p>
    );
  }
  const failed = status === "failed";
  const Icon = failed ? STATUS_ICONS.error : STATUS_ICONS.warning;
  return (
    <p
      className={cn(
        CELL_LINE,
        failed ? "ui:text-destructive" : "ui:text-muted-foreground",
      )}
    >
      <Icon
        aria-hidden
        className={cn(
          "ui:size-3.5 ui:shrink-0",
          failed ? "ui:text-destructive" : "ui:text-warning",
        )}
      />
      {failed ? "Run failed" : "Yet to run"}
    </p>
  );
}
