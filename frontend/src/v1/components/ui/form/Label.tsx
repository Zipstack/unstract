import { cn } from "@v1/lib/cn";
import { Label as LabelPrimitive } from "radix-ui";
import type { ComponentProps, JSX } from "react";

/** The label's text classes; the toggles reuse them beside their controls. */
export const LABEL_CLASS =
  "ui:text-body-small ui:font-medium ui:text-foreground ui:select-none ui:data-disabled:opacity-50";

export type LabelProps = ComponentProps<typeof LabelPrimitive.Root>;

/** A control's visible name; pair it with the control through `htmlFor`, or let Field do it. */
export function Label({ className, ...props }: LabelProps): JSX.Element {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn(LABEL_CLASS, className)}
      {...props}
    />
  );
}
