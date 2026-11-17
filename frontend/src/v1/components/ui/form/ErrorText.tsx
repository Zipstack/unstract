import { cn } from "@v1/lib/cn";
import type { ComponentProps, JSX } from "react";

export type ErrorTextProps = ComponentProps<"p">;

/** A validation message. role="alert" makes screen readers announce it when it is rendered, so render it only while there is an error. */
export function ErrorText({
  className,
  ...props
}: ErrorTextProps): JSX.Element {
  return (
    <p
      role="alert"
      data-slot="error-text"
      className={cn("ui:text-caption ui:text-destructive", className)}
      {...props}
    />
  );
}
