import { cn } from "@v1/lib/cn";
import { ChevronRight } from "lucide-react";
import type { JSX, ReactNode } from "react";
import { STEP_STATE_TEXT, StepMarker, type StepState } from "./stepState";

export type ChecklistStep = Readonly<{
  id: string;
  label: string;
  /** The line under the label: what was chosen, or why it is not done. */
  value?: ReactNode;
  state: StepState;
  disabled?: boolean;
}>;

export type ChecklistProps = Readonly<{
  steps: readonly ChecklistStep[];
  "aria-label": string;
  /** The step whose panel is open; marked `aria-current="step"`. */
  currentId?: string;
  /** Makes each step a button that opens it. Without it the list is read-only. */
  onSelect?: (id: string) => void;
  className?: string;
}>;

const CARD_BY_STATE: Record<StepState, string> = {
  done: "ui:border-border ui:bg-card",
  "in-progress": "ui:border-primary/30 ui:bg-primary-muted",
  "not-started": "ui:border-border ui:bg-card",
  failed: "ui:border-destructive/30 ui:bg-destructive/10",
};

/**
 * The guided-setup checklist (frames 756:1190, 758:20028, 789:3765): one card
 * per step with a marker, label and value line. Each state is also read out
 * as text after the label.
 */
export function Checklist({
  steps,
  currentId,
  onSelect,
  className,
  ...named
}: ChecklistProps): JSX.Element {
  return (
    <ol
      data-slot="checklist"
      className={cn(
        "ui:m-0 ui:flex ui:list-none ui:flex-col ui:gap-2 ui:p-0",
        className,
      )}
      {...named}
    >
      {steps.map((step, index) => {
        const current = step.id === currentId ? "step" : undefined;
        const body = (
          <>
            <StepMarker state={step.state} index={index} />
            <span className="ui:flex ui:min-w-0 ui:flex-1 ui:flex-col ui:gap-0.5">
              <span className="ui:text-body ui:font-semibold ui:text-foreground">
                {step.label}
                <span className="ui:sr-only">{`, ${STEP_STATE_TEXT[step.state]}`}</span>
              </span>
              {step.value != null && (
                <span className="ui:truncate ui:text-caption ui:text-muted-foreground">
                  {step.value}
                </span>
              )}
            </span>
          </>
        );
        const card = cn(
          "ui:box-border ui:flex ui:w-full ui:items-center ui:gap-3 ui:rounded-lg ui:border ui:border-solid ui:px-3 ui:py-2.75 ui:text-left ui:font-sans",
          CARD_BY_STATE[step.state],
        );
        return (
          <li key={step.id} data-state={step.state}>
            {onSelect ? (
              <button
                type="button"
                aria-current={current}
                disabled={step.disabled}
                onClick={() => onSelect(step.id)}
                className={cn(
                  card,
                  "ui:cursor-pointer ui:outline-none ui:focus-visible:focus-ring ui:not-disabled:hover:border-primary/50 ui:disabled:cursor-not-allowed ui:disabled:opacity-50",
                )}
              >
                {body}
                <ChevronRight
                  aria-hidden
                  className="ui:size-3.5 ui:shrink-0 ui:text-muted-foreground"
                />
              </button>
            ) : (
              <div aria-current={current} className={card}>
                {body}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
