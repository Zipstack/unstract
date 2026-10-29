import { cn } from "@v1/lib/cn";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps, JSX } from "react";

/*
 * The one border, radius, padding and focus treatment for every text control.
 * The ring follows the control (data-slot="control"), not the whole frame, so
 * tabbing to an adornment button rings only that button. Invalid swaps the
 * ring colour, so an invalid field keeps a destructive ring while focused.
 */
export const fieldFrameVariants = cva(
  [
    "ui:box-border ui:flex ui:w-full ui:min-w-0 ui:gap-2 ui:rounded-md ui:border ui:border-input ui:bg-transparent ui:text-body ui:text-foreground ui:transition-[border-color,box-shadow]",
    "ui:hover:border-muted-foreground",
    "ui:has-[[data-slot=control]:focus-visible]:focus-ring",
    "ui:data-readonly:border-input ui:data-readonly:bg-muted",
    "ui:data-invalid:border-destructive ui:data-invalid:[--ring:var(--destructive)]",
    "ui:data-disabled:pointer-events-none ui:data-disabled:opacity-50",
  ],
  {
    variants: {
      multiline: {
        false: "ui:h-8 ui:items-center ui:px-3",
        true: "ui:items-stretch",
      },
    },
    defaultVariants: { multiline: false },
  },
);

/** Classes for the native input or textarea inside a frame; the frame draws the box. */
export const fieldControlClass =
  "ui:min-w-0 ui:flex-1 ui:border-0 ui:bg-transparent ui:p-0 ui:text-body ui:text-foreground ui:outline-none ui:placeholder:text-muted-foreground ui:disabled:cursor-not-allowed";

export type FieldFrameProps = ComponentProps<"div"> &
  VariantProps<typeof fieldFrameVariants> &
  Readonly<{
    invalid?: boolean;
    disabled?: boolean;
    readOnly?: boolean;
  }>;

const flag = (on: boolean | undefined) => (on ? "" : undefined);

export function FieldFrame({
  invalid,
  disabled,
  readOnly,
  multiline,
  className,
  ...props
}: FieldFrameProps): JSX.Element {
  return (
    <div
      data-slot="field-frame"
      data-invalid={flag(invalid)}
      data-disabled={flag(disabled)}
      data-readonly={flag(readOnly)}
      className={cn(fieldFrameVariants({ multiline }), className)}
      {...props}
    />
  );
}
