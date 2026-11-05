import { cn } from "@v1/lib/cn";
import { Check } from "lucide-react";
import type { JSX } from "react";

export type StepProgressProps = Readonly<{
  steps: readonly string[];
  /** Index of the step in progress; equal to `steps.length` when all are done. */
  current: number;
  "aria-label": string;
  className?: string;
}>;

type StepState = "done" | "current" | "upcoming";

function stateOf(index: number, current: number): StepState {
  if (index < current) {
    return "done";
  }
  return index === current ? "current" : "upcoming";
}

const STATE_TEXT: Record<StepState, string> = {
  done: "completed",
  current: "current",
  upcoming: "not started",
};

/** Ordered steps with done, current and upcoming states. */
export function StepProgress({
  steps,
  current,
  className,
  ...named
}: StepProgressProps): JSX.Element {
  return (
    <ol
      data-slot="step-progress"
      className={cn(
        "ui:m-0 ui:flex ui:list-none ui:flex-wrap ui:gap-4 ui:p-0",
        className,
      )}
      {...named}
    >
      {steps.map((label, index) => {
        const state = stateOf(index, current);
        return (
          <li
            key={label}
            data-state={state}
            aria-current={state === "current" ? "step" : undefined}
            className="ui:flex ui:items-center ui:gap-2 ui:text-body-small"
          >
            <span
              aria-hidden
              className={cn(
                "ui:inline-flex ui:size-5 ui:shrink-0 ui:items-center ui:justify-center ui:rounded-full ui:border ui:text-caption",
                state === "done" &&
                  "ui:border-primary ui:bg-primary ui:text-primary-foreground",
                state === "current" && "ui:border-primary ui:text-primary",
                state === "upcoming" &&
                  "ui:border-border ui:text-muted-foreground",
              )}
            >
              {state === "done" ? <Check className="ui:size-3" /> : index + 1}
            </span>
            <span
              className={cn(
                state === "upcoming"
                  ? "ui:text-muted-foreground"
                  : "ui:text-foreground",
                state === "current" && "ui:font-medium",
              )}
            >
              {label}
              <span className="ui:sr-only">{`, ${STATE_TEXT[state]}`}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
