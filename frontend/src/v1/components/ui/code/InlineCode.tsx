import { cn } from "@v1/lib/cn";
import type { ComponentProps, JSX } from "react";
import { MONO } from "./CodeLines";

export type InlineCodeProps = ComponentProps<"code"> &
  Readonly<{
    /**
     * `chip` (default) sets the text on a muted chip, for code in running
     * text. `plain` is the mono font alone, for IDs and token counts in
     * tables and stats.
     */
    variant?: "chip" | "plain";
  }>;

/** Mono text inside other text: code spans, IDs, token counts. */
export function InlineCode({
  variant = "chip",
  className,
  ...props
}: InlineCodeProps): JSX.Element {
  return (
    <code
      data-slot="inline-code"
      data-variant={variant}
      className={cn(
        MONO,
        variant === "chip" &&
          "ui:rounded-sm ui:bg-muted ui:px-1 ui:py-0.5 ui:text-foreground",
        className,
      )}
      {...props}
    />
  );
}
