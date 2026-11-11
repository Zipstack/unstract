import { cn } from "@v1/lib/cn";
import { Check, TriangleAlert } from "lucide-react";
import type { JSX } from "react";

/** The four states a Stepper or Checklist step can be in. */
export const STEP_STATES = [
  "done",
  "in-progress",
  "not-started",
  "failed",
] as const;

export type StepState = (typeof STEP_STATES)[number];

/** Read to screen readers after the label, so a state is never colour alone. */
export const STEP_STATE_TEXT: Record<StepState, string> = {
  done: "done",
  "in-progress": "in progress",
  "not-started": "not started",
  failed: "failed",
};

/*
 * The 22px round marker of frames 756:1190, 758:20028 and 789:3765: a check
 * when done, a warning glyph when failed, otherwise the step number.
 */
export function StepMarker({
  state,
  index,
}: Readonly<{ state: StepState; index: number }>): JSX.Element {
  return (
    <span
      aria-hidden
      data-slot="step-marker"
      className={cn(
        "ui:inline-flex ui:size-5.5 ui:shrink-0 ui:items-center ui:justify-center ui:rounded-full ui:text-caption ui:font-semibold",
        (state === "done" || state === "in-progress") &&
          "ui:bg-primary ui:text-primary-foreground",
        state === "not-started" && "ui:bg-muted ui:text-muted-foreground",
        state === "failed" &&
          "ui:bg-destructive ui:text-destructive-foreground",
      )}
    >
      {state === "done" && <Check className="ui:size-3" />}
      {state === "failed" && <TriangleAlert className="ui:size-3" />}
      {(state === "in-progress" || state === "not-started") && index + 1}
    </span>
  );
}
