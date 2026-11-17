import { cn } from "@v1/lib/cn";
import { Progress as RadixProgress } from "radix-ui";
import type { JSX } from "react";

type Named =
  | Readonly<{ "aria-label": string; "aria-labelledby"?: never }>
  | Readonly<{ "aria-labelledby": string; "aria-label"?: never }>;

export type ProgressBarProps = Named &
  Readonly<{
    /** 0 to `max`; leave it out (or null) while the total is unknown. */
    value?: number | null;
    max?: number;
    className?: string;
  }>;

/** A 6px rounded track with a primary fill (frame 757:310). The name is required. */
export function ProgressBar({
  value = null,
  max = 100,
  className,
  ...named
}: ProgressBarProps): JSX.Element {
  const indeterminate = value === null;
  // Radix rejects a max that is not a positive number, and a value that is not
  // finite; an empty batch (0 of 0, or `done / total * 100` with total 0) shows
  // as an empty bar rather than NaN.
  const validMax = Number.isFinite(max) && max > 0;
  const total = validMax ? max : 100;
  const clamped =
    indeterminate || !validMax || !Number.isFinite(value)
      ? 0
      : Math.min(Math.max(value, 0), total);
  return (
    <RadixProgress.Root
      value={indeterminate ? null : clamped}
      max={total}
      data-slot="progress-bar"
      className={cn(
        "ui:relative ui:h-1.5 ui:w-full ui:overflow-hidden ui:rounded-full ui:bg-muted",
        className,
      )}
      {...named}
    >
      <RadixProgress.Indicator
        style={{ "--progress": indeterminate ? 0.4 : clamped / total }}
        className={cn(
          "ui:h-full ui:w-[calc(var(--progress)*100%)] ui:rounded-full ui:bg-primary ui:transition-[width] ui:motion-reduce:transition-none",
          indeterminate && "ui:motion-safe:animate-pulse",
        )}
      />
    </RadixProgress.Root>
  );
}
