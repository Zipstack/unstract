import { zodResolver } from "@hookform/resolvers/zod";
import { useCallback, useEffect } from "react";
import {
  type DefaultValues,
  type FieldValues,
  get,
  type Path,
  type UseFormReturn,
  useForm,
} from "react-hook-form";
import type { z } from "zod";

/** react-hook-form with the schema as resolver: fields validate on blur, and a failed submit focuses the first invalid field. */
export function useAppForm<I extends FieldValues, O>({
  schema,
  defaultValues,
}: {
  schema: z.ZodType<O, I>;
  defaultValues: DefaultValues<I>;
}): UseFormReturn<I, unknown, O> {
  return useForm<I, unknown, O>({
    resolver: zodResolver(schema),
    defaultValues,
    mode: "onBlur",
    shouldFocusError: true,
  });
}

/** The backend's error body (drf_standardized_errors). */
export type ServerErrorBody = Readonly<{
  type: "validation_error" | "client_error" | "server_error";
  errors: readonly Readonly<{
    code: string;
    detail: string;
    attr: string | null;
  }>[];
}>;

/** The form-level error key that applyServerErrors sets; FormFooter shows it. */
export const SERVER_ERROR = "root.server";

/**
 * Puts each server error on the field its `attr` names (a dotted attr such as
 * `rows.0.key` is a react-hook-form path). An error with no attr, a
 * non_field_errors attr, an attr the form does not hold, or any error of a
 * non-validation response becomes one form-level message.
 */
// ponytail: reads the raw backend body; switch to P0-T05's normalised error when it lands.
export function applyServerErrors<T extends FieldValues>(
  form: Pick<UseFormReturn<T>, "getValues" | "setError">,
  body: ServerErrorBody,
): void {
  const values = form.getValues();
  const formLevel: string[] = [];
  for (const { attr, detail } of body.errors) {
    const onField =
      body.type === "validation_error" &&
      attr !== null &&
      get(values, attr) !== undefined;
    if (onField) {
      form.setError(attr as Path<T>, { type: "server", message: detail });
    } else {
      formLevel.push(detail);
    }
  }
  if (formLevel.length > 0) {
    form.setError(SERVER_ERROR as Path<T>, {
      type: "server",
      message: formLevel.join(" "),
    });
  }
}

/**
 * While `dirty`, the browser asks before the tab closes, and the returned
 * function asks `confirm` before a dialog closes or the caller navigates away.
 * It resolves true when leaving is fine.
 */
// ponytail: no router blocking; v0 mounts a BrowserRouter, which has no blocker. Add useBlocker when P0-T01 moves to a data router.
export function useLeaveGuard(
  dirty: boolean,
  confirm: () => Promise<boolean>,
): () => Promise<boolean> {
  useEffect(() => {
    if (!dirty) {
      return;
    }
    const ask = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", ask);
    return () => window.removeEventListener("beforeunload", ask);
  }, [dirty]);
  return useCallback(async () => (dirty ? confirm() : true), [dirty, confirm]);
}
