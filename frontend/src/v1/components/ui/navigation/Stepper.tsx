import { cn } from "@v1/lib/cn";
import type { JSX, ReactNode } from "react";
import { STEP_STATE_TEXT, StepMarker, type StepState } from "./stepState";

export type StepperStep = Readonly<{
  id: string;
  label: string;
  /** An optional second line: a count, a duration, a reason. */
  value?: ReactNode;
  state: StepState;
}>;

export type StepperProps = Readonly<{
  steps: readonly StepperStep[];
  "aria-label": string;
  className?: string;
}>;

/**
 * Stages in a row, joined by a rule that turns primary once the step before it
 * is done. The first in-progress step is `aria-current="step"`; each state is
 * read out as text after its label.
 */
export function Stepper({
  steps,
  className,
  ...named
}: StepperProps): JSX.Element {
  const current = steps.find((step) => step.state === "in-progress")?.id;
  return (
    <ol
      data-slot="stepper"
      className={cn(
        "ui:m-0 ui:flex ui:list-none ui:items-start ui:gap-3 ui:p-0",
        className,
      )}
      {...named}
    >
      {steps.map((step, index) => (
        <li
          key={step.id}
          data-state={step.state}
          aria-current={step.id === current ? "step" : undefined}
          className="ui:flex ui:min-w-0 ui:flex-1 ui:items-start ui:gap-3 ui:last:flex-none"
        >
          <span className="ui:flex ui:min-w-0 ui:items-start ui:gap-2">
            <StepMarker state={step.state} index={index} />
            <span className="ui:flex ui:min-w-0 ui:flex-col ui:gap-0.5">
              <span
                className={cn(
                  "ui:text-body-small ui:font-semibold",
                  step.state === "not-started"
                    ? "ui:text-muted-foreground"
                    : "ui:text-foreground",
                  step.state === "failed" && "ui:text-destructive",
                )}
              >
                {step.label}
                <span className="ui:sr-only">{`, ${STEP_STATE_TEXT[step.state]}`}</span>
              </span>
              {step.value !== undefined && (
                <span className="ui:text-caption ui:text-muted-foreground">
                  {step.value}
                </span>
              )}
            </span>
          </span>
          {index < steps.length - 1 && (
            <span
              aria-hidden
              data-slot="stepper-rule"
              className={cn(
                "ui:mt-2.75 ui:h-px ui:min-w-4 ui:flex-1",
                step.state === "done" ? "ui:bg-primary" : "ui:bg-border",
              )}
            />
          )}
        </li>
      ))}
    </ol>
  );
}
