import { Button } from "@v1/components/ui/button";
import { ErrorText } from "@v1/components/ui/form";
import type { JSX } from "react";
import {
  type Control,
  type FieldErrors,
  type FieldValues,
  get,
  type UseFormReturn,
  useFormState,
} from "react-hook-form";
import { errorLeaves, isMounted, SERVER_ERROR } from "./use-app-form";

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

/**
 * The save bar: what changed, Save changes (submits the form) and Discard
 * (back to the form's default values). Errors with no field on screen, and the
 * server's form-level error, show here while the form has changes. Only schema
 * errors on shown fields disable Save; server errors clear on a submit, so
 * they never do.
 */
// ponytail: plain buttons; swap to the v1 Button when it exists.
export function FormFooter<T extends FieldValues>({
  form,
}: Readonly<{ form: UseFormReturn<T, unknown, FieldValues> }>): JSX.Element {
  const { dirtyFields, errors, isSubmitting } = useFormState({
    control: form.control,
  });
  const dirty = countDirty(dirtyFields);
  const control = form.control as Control<FieldValues>;
  const { root: _root, ...rest } = errors as FieldErrors<FieldValues>;
  const leaves = errorLeaves(rest);
  // A server error clears only on that field's change or the next submit; a
  // disabled or read-only field allows neither, so it must not lock Save.
  const hasFieldErrors = leaves.some(
    ([path, e]) => e.type !== "server" && isMounted(control, path),
  );
  const formLevel = [
    ...leaves
      .filter(([path]) => !isMounted(control, path))
      .map(([, e]) => (typeof e.message === "string" ? e.message : "")),
    get(errors, SERVER_ERROR)?.message,
  ].filter((m): m is string => Boolean(m));
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
        {dirty > 0 && formLevel.length > 0 ? (
          <ErrorText>{formLevel.join(" ")}</ErrorText>
        ) : null}
      </div>
      <Button
        variant="outline"
        data-testid="form-footer-discard"
        disabled={dirty === 0 || isSubmitting}
        onClick={() => form.reset()}
      >
        Discard
      </Button>
      <Button
        type="submit"
        data-testid="form-footer-save"
        loading={isSubmitting}
        disabled={!isSubmitting && (dirty === 0 || hasFieldErrors)}
      >
        Save changes
      </Button>
    </div>
  );
}
