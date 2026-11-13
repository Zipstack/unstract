import { cn } from "@v1/lib/cn";
import type { ComponentProps, JSX } from "react";

export type HelperTextProps = ComponentProps<"p">;

/** Guidance under a control; the control points at its id through aria-describedby. */
export function HelperText({
  className,
  ...props
}: HelperTextProps): JSX.Element {
  return (
    <p
      data-slot="helper-text"
      className={cn("ui:text-caption ui:text-muted-foreground", className)}
      {...props}
    />
  );
}
