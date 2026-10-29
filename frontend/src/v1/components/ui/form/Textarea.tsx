import { cn } from "@v1/lib/cn";
import type { ComponentProps, JSX } from "react";
import { FieldFrame, fieldControlClass } from "./FieldFrame";
import { useFieldControl } from "./field-context";

export type TextareaProps = ComponentProps<"textarea"> &
  Readonly<{
    invalid?: boolean;
    /** Classes for the native textarea; `className` styles the frame. */
    controlClassName?: string;
  }>;

/** A multi-line text control the user can resize vertically. */
export function Textarea({
  invalid,
  disabled,
  readOnly,
  id,
  className,
  controlClassName,
  "aria-describedby": describedBy,
  ...props
}: TextareaProps): JSX.Element {
  const control = useFieldControl({
    id,
    "aria-describedby": describedBy,
    invalid,
    disabled,
    readOnly,
  });
  return (
    <FieldFrame
      multiline
      invalid={control.invalid}
      disabled={control.disabled}
      readOnly={control.readOnly}
      className={className}
    >
      <textarea
        data-slot="control"
        id={control.id}
        aria-describedby={control["aria-describedby"]}
        aria-invalid={control["aria-invalid"]}
        disabled={control.disabled}
        readOnly={control.readOnly}
        className={cn(
          fieldControlClass,
          "ui:min-h-16 ui:resize-y ui:px-3 ui:py-2",
          controlClassName,
        )}
        {...props}
      />
    </FieldFrame>
  );
}
