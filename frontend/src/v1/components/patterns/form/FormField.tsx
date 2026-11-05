import { Field, type FieldProps } from "@v1/components/ui/form";
import type { JSX, ReactNode } from "react";
import {
  type ControllerRenderProps,
  type FieldPath,
  type FieldValues,
  type UseFormReturn,
  useController,
} from "react-hook-form";

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
  return (
    <Field {...fieldProps} error={fieldState.error?.message}>
      {children(field)}
    </Field>
  );
}
