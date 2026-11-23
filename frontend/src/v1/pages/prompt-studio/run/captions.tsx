import { InlineCode } from "@v1/components/ui/code";
import { InlineAlert, Spinner } from "@v1/components/ui/feedback";
import { cn } from "@v1/lib/cn";
import { SHELL_ICONS, STATUS_ICONS } from "@v1/lib/icons";
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
      className="ui:m-0 ui:flex ui:min-w-0 ui:items-center ui:gap-1.5 ui:text-body-small"
    >
      {onOpen ? (
        <button
          type="button"
          onClick={onOpen}
          className="ui:inline-flex ui:cursor-pointer ui:items-center ui:gap-1.5 ui:rounded-sm ui:border-0 ui:bg-transparent ui:p-0 ui:text-primary ui:hover:underline ui:focus-visible:focus-ring"
        >
          {body}
        </button>
      ) : (
        <span className="ui:inline-flex ui:items-center ui:gap-1.5 ui:text-primary">
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
  return (
    <InlineAlert
      kind="info"
      title="Single pass extraction is on"
      className="ui:bg-primary-muted"
    >
      All prompts are sent to the model in one request. Cost drops, but
      per-prompt timing and per-prompt retries are no longer available.
    </InlineAlert>
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
        "ui:m-0 ui:flex ui:flex-wrap ui:gap-x-3 ui:text-caption ui:text-muted-foreground",
        className,
      )}
    >
      <InlineCode variant="plain">Tokens: {formatTokens(tokens)}</InlineCode>
      <InlineCode variant="plain">Time: {formatSeconds(seconds)}</InlineCode>
      <InlineCode variant="plain">Cost: {formatCost(cost)}</InlineCode>
    </p>
  );
}

export type CellRunStateProps = Readonly<{
  /** `running` covers queued requests too; `idle` means it never ran. */
  status: "running" | "idle";
}>;

/** A model-grid cell with no output to show: "Running…" or "Yet to run". */
export function CellRunState({ status }: CellRunStateProps): JSX.Element {
  const WarningIcon = STATUS_ICONS.warning;
  return status === "running" ? (
    <p className="ui:m-0 ui:flex ui:items-center ui:gap-2 ui:text-body-small ui:text-muted-foreground">
      <Spinner />
      Running…
    </p>
  ) : (
    <p className="ui:m-0 ui:flex ui:items-center ui:gap-2 ui:text-body-small ui:text-muted-foreground">
      <WarningIcon
        aria-hidden
        className="ui:size-3.5 ui:shrink-0 ui:text-warning"
      />
      Yet to run
    </p>
  );
}
