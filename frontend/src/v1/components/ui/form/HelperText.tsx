import { cn } from "@v1/lib/cn";
import type { ComponentProps, JSX } from "react";

/** The helper text's classes; the toggles reuse them for their descriptions. */
export const HELPER_TEXT_CLASS = "ui:text-caption ui:text-muted-foreground";

export type HelperTextProps = ComponentProps<"p">;

/** Guidance under a control; the control points at its id through aria-describedby. */
export function HelperText({
  className,
  ...props
}: HelperTextProps): JSX.Element {
  return (
    <p
      data-slot="helper-text"
      className={cn(HELPER_TEXT_CLASS, className)}
      {...props}
    />
  );
}
