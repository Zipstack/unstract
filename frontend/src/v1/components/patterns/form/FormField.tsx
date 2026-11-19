import { Field, type FieldProps } from "@v1/components/ui/form";
import { type JSX, type ReactNode, useEffect } from "react";
import {
  type Control,
  type ControllerRenderProps,
  type FieldPath,
  type FieldValues,
  type UseFormReturn,
  useController,
} from "react-hook-form";
import { isMounted } from "./use-app-form";

export type FormFieldProps<
  T extends FieldValues,
  N extends FieldPath<T>,
> = Omit<FieldProps, "children" | "error" | "invalid"> &
  Readonly<{
    form: UseFormReturn<T, unknown, FieldValues>;
    name: N;
    /** Renders the control from the field's value, handlers and ref. */
    children: (field: ControllerRenderProps<T, N>) => ReactNode;
  }>;

/** A Field bound to one form value: its error shows under the control and marks it invalid. */
export function FormField<T extends FieldValues, N extends FieldPath<T>>({
  form,
  name,
  children,
  ...fieldProps
}: FormFieldProps<T, N>): JSX.Element {
  const { field, fieldState } = useController({ control: form.control, name });
  // A hidden field cannot show its error, so drop it; a submit validates again
  // and an error that still stands shows in the footer. Check after the commit:
  // a field-array row that moved, or the row that took a removed row's path,
  // mounts the same path again and keeps its error.
  const { clearErrors, control } = form;
  useEffect(
    () => () => {
      queueMicrotask(() => {
        if (!isMounted(control as Control<FieldValues>, name)) {
          clearErrors(name);
        }
      });
    },
    [clearErrors, control, name],
  );
  return (
    <Field {...fieldProps} error={fieldState.error?.message}>
      {children(field)}
    </Field>
  );
}
