import { ErrorText } from "@v1/components/ui/form";
import type { JSX } from "react";
import {
  type FieldValues,
  type UseFormReturn,
  useFormState,
} from "react-hook-form";

/** Leaves (true values) in react-hook-form's nested dirtyFields. */
function countDirty(node: unknown): number {
  if (node === true) {
    return 1;
  }
  if (node && typeof node === "object") {
    return Object.values(node).reduce<number>((n, v) => n + countDirty(v), 0);
  }
  return 0;
}

function status(
  submitting: boolean,
  dirty: number,
  fieldErrors: boolean,
): string {
  if (submitting) {
    return "Saving";
  }
  if (dirty === 0) {
    return "No changes";
  }
  if (fieldErrors) {
    return "Cannot save";
  }
  return `${dirty} unsaved change${dirty === 1 ? "" : "s"}`;
}

const button =
  "ui:h-8 ui:cursor-pointer ui:rounded-md ui:px-3 ui:text-body ui:disabled:pointer-events-none ui:disabled:opacity-50 ui:focus-visible:focus-ring";

/** The save bar: what changed, Save changes (submits the form) and Discard (back to the last saved values). */
// ponytail: plain buttons; swap to the v1 Button when P1-T01 lands.
export function FormFooter<T extends FieldValues>({
  form,
}: Readonly<{ form: UseFormReturn<T, unknown, FieldValues> }>): JSX.Element {
  const { dirtyFields, errors, isSubmitting } = useFormState({
    control: form.control,
  });
  const dirty = countDirty(dirtyFields);
  const { root, ...fieldErrors } = errors;
  const hasFieldErrors = Object.keys(fieldErrors).length > 0;
  const text = status(isSubmitting, dirty, hasFieldErrors);
  return (
    <div
      data-slot="form-footer"
      className="ui:flex ui:items-center ui:gap-3 ui:border-t ui:pt-3"
    >
      <div className="ui:grid ui:flex-1 ui:gap-1">
        <output className="ui:text-caption ui:text-muted-foreground">
          {text}
        </output>
        {root?.server?.message ? (
          <ErrorText>{root.server.message}</ErrorText>
        ) : null}
      </div>
      <button
        type="button"
        className={`${button} ui:border ui:bg-transparent`}
        disabled={dirty === 0 || isSubmitting}
        onClick={() => form.reset()}
      >
        Discard
      </button>
      <button
        type="submit"
        className={`${button} ui:border-0 ui:bg-primary ui:text-primary-foreground`}
        disabled={dirty === 0 || isSubmitting || hasFieldErrors}
      >
        Save changes
      </button>
    </div>
  );
}
