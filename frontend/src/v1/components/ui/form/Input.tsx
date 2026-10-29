import { cn } from "@v1/lib/cn";
import type { ComponentProps, JSX, ReactNode } from "react";
import { FieldFrame, fieldControlClass } from "./FieldFrame";
import { useFieldControl } from "./field-context";

export type InputProps = Omit<ComponentProps<"input">, "prefix"> &
  Readonly<{
    /** Icon before the value. */
    leading?: ReactNode;
    /** Icon or FieldAction after the value. */
    trailing?: ReactNode;
    /** Text before the value, such as "https://". */
    prefix?: ReactNode;
    /** Text after the value, such as "pages". */
    suffix?: ReactNode;
    invalid?: boolean;
    /** Classes for the native input; `className` styles the frame. */
    controlClassName?: string;
  }>;

const iconSlot =
  "ui:flex ui:shrink-0 ui:items-center ui:text-muted-foreground ui:[&>svg]:size-4";
const textSlot =
  "ui:shrink-0 ui:whitespace-nowrap ui:text-muted-foreground ui:select-none";

/** A single-line text control, 32 tall, with optional adornments. */
export function Input({
  leading,
  trailing,
  prefix,
  suffix,
  invalid,
  disabled,
  readOnly,
  id,
  className,
  controlClassName,
  "aria-describedby": describedBy,
  ...props
}: InputProps): JSX.Element {
  const control = useFieldControl({
    id,
    "aria-describedby": describedBy,
    invalid,
    disabled,
    readOnly,
  });
  return (
    <FieldFrame
      invalid={control.invalid}
      disabled={control.disabled}
      readOnly={control.readOnly}
      className={className}
    >
      {leading ? (
        <span data-slot="field-leading" className={iconSlot}>
          {leading}
        </span>
      ) : null}
      {prefix ? (
        <span data-slot="field-prefix" className={textSlot}>
          {prefix}
        </span>
      ) : null}
      <input
        data-slot="control"
        id={control.id}
        aria-describedby={control["aria-describedby"]}
        aria-invalid={control["aria-invalid"]}
        disabled={control.disabled}
        readOnly={control.readOnly}
        className={cn(fieldControlClass, "ui:h-full", controlClassName)}
        {...props}
      />
      {suffix ? (
        <span data-slot="field-suffix" className={textSlot}>
          {suffix}
        </span>
      ) : null}
      {trailing ? (
        <span data-slot="field-trailing" className={iconSlot}>
          {trailing}
        </span>
      ) : null}
    </FieldFrame>
  );
}
