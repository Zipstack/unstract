import { cn } from "@v1/lib/cn";
import type { ComponentProps, JSX } from "react";

export type ButtonGroupProps = ComponentProps<"div">;

/** Buttons joined into one shape: shared borders, one outer radius. */
export function ButtonGroup({
  className,
  ...props
}: ButtonGroupProps): JSX.Element {
  return (
    // biome-ignore lint/a11y/useSemanticElements: a fieldset needs a legend and adds a border; a labelled group of buttons is the documented pattern.
    <div
      role="group"
      data-slot="button-group"
      className={cn(
        "ui:inline-flex ui:items-stretch ui:*:rounded-none ui:*:first:rounded-s-md ui:*:last:rounded-e-md ui:*:not-first:-ms-px ui:*:focus-visible:z-10",
        className,
      )}
      {...props}
    />
  );
}
