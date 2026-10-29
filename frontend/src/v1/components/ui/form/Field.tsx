import { cn } from "@v1/lib/cn";
import { type JSX, type ReactNode, useId, useMemo } from "react";
import { ErrorText } from "./ErrorText";
import { FieldContext, type FieldContextValue } from "./field-context";
import { HelperText } from "./HelperText";
import { Label } from "./Label";

export type FieldProps = Readonly<{
  label: ReactNode;
  helperText?: ReactNode;
  /** Shown as ErrorText and marks the control invalid unless `invalid` says otherwise. */
  error?: ReactNode;
  invalid?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  /** The control's id; generated when omitted. */
  id?: string;
  className?: string;
  children: ReactNode;
}>;

/** Label, control, helper and error text, wired together: the label names the control and the control is described by the texts. */
export function Field({
  label,
  helperText,
  error,
  invalid,
  disabled = false,
  readOnly = false,
  id,
  className,
  children,
}: FieldProps): JSX.Element {
  const generatedId = useId();
  const controlId = id ?? `${generatedId}control`;
  // Derived from the control id, so a caller that passes `id` gets stable ids.
  const helperId = helperText ? `${controlId}-helper` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const isInvalid = invalid ?? Boolean(error);

  const context = useMemo<FieldContextValue>(
    () => ({
      controlId,
      describedBy: [helperId, errorId].filter(Boolean).join(" ") || undefined,
      invalid: isInvalid,
      disabled,
      readOnly,
    }),
    [controlId, helperId, errorId, isInvalid, disabled, readOnly],
  );

  return (
    <FieldContext value={context}>
      <div data-slot="field" className={cn("ui:grid ui:gap-1.5", className)}>
        <Label htmlFor={controlId} data-disabled={disabled ? "" : undefined}>
          {label}
        </Label>
        {children}
        {helperText ? (
          <HelperText id={helperId}>{helperText}</HelperText>
        ) : null}
        {error ? <ErrorText id={errorId}>{error}</ErrorText> : null}
      </div>
    </FieldContext>
  );
}
