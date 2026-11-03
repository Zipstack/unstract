import { cn } from "@v1/lib/cn";
import { Progress } from "radix-ui";
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
  const clamped = indeterminate ? 0 : Math.min(Math.max(value, 0), max);
  return (
    <Progress.Root
      value={indeterminate ? null : clamped}
      max={max}
      data-slot="progress-bar"
      className={cn(
        "ui:relative ui:h-1.5 ui:w-full ui:overflow-hidden ui:rounded-full ui:bg-muted",
        className,
      )}
      {...named}
    >
      <Progress.Indicator
        style={{ "--progress": indeterminate ? 0.4 : clamped / max }}
        className={cn(
          "ui:h-full ui:w-[calc(var(--progress)*100%)] ui:rounded-full ui:bg-primary ui:transition-[width] ui:motion-reduce:transition-none",
          indeterminate && "ui:animate-pulse",
        )}
      />
    </Progress.Root>
  );
}
