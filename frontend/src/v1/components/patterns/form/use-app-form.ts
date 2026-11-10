import { zodResolver } from "@hookform/resolvers/zod";
import { useCallback, useEffect } from "react";
import {
  type Control,
  type DefaultValues,
  type FieldValues,
  get,
  type Path,
  type UseFormReturn,
  useForm,
} from "react-hook-form";
import type { z } from "zod";

/**
 * react-hook-form with the schema as resolver. A field validates when it first
 * loses focus, then on every change; after a submit every field validates on
 * change. A failed submit focuses the first invalid field.
 *
 * `defaultValues` are the saved values: the change count and Discard compare
 * against them. They are read once, so call `form.reset(saved)` after a
 * successful save, and `form.reset(record)` when a record loads after mount.
 */
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
    mode: "onTouched",
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

const FALLBACK = "Could not save. Try again.";

/** True when a FormField (or any registered control) for `path` is on screen. */
export function isMounted(
  control: Control<FieldValues>,
  path: string,
): boolean {
  // ponytail: reads react-hook-form's field registry; form.test.tsx pins the behaviour across upgrades.
  return get(control._fields, path)?._f?.mount === true;
}

function isStandardBody(body: unknown): body is ServerErrorBody {
  const b = body as ServerErrorBody | null;
  return typeof b?.type === "string" && Array.isArray(b.errors);
}

/** Any other error body: `{detail}` from the middleware, `{error}` from the SDK handler. */
function otherMessage(body: unknown): string | undefined {
  const b = body as Record<string, unknown> | null;
  return [b?.detail, b?.error, b?.message].find(
    (text): text is string => typeof text === "string" && text.trim() !== "",
  );
}

/**
 * Puts each server error under the field its `attr` names (a dotted attr such
 * as `rows.0.key` is a react-hook-form path), when that field is on screen.
 * Every other error (no attr, non_field_errors, an attr with no field shown, or
 * a non-validation response) joins one form-level message. A body of any other
 * shape, or one with nothing to show, still sets a form-level message.
 */
// ponytail: reads the raw backend body; switch to the shared HTTP client's normalised error when it exists.
export function applyServerErrors<T extends FieldValues>(
  form: Pick<UseFormReturn<T, unknown, FieldValues>, "control" | "setError">,
  body: unknown,
): void {
  const byField = new Map<string, string[]>();
  const formLevel: string[] = [];
  const standard = isStandardBody(body) ? body : undefined;
  for (const entry of standard?.errors ?? []) {
    const { attr, detail } = entry ?? {};
    if (typeof detail !== "string" || !detail.trim()) {
      continue;
    }
    const onField =
      standard?.type === "validation_error" &&
      typeof attr === "string" &&
      isMounted(form.control as Control<FieldValues>, attr);
    if (onField) {
      byField.set(attr, [...(byField.get(attr) ?? []), detail]);
    } else {
      formLevel.push(detail);
    }
  }
  for (const [attr, details] of byField) {
    form.setError(attr as Path<T>, {
      type: "server",
      message: details.join(" "),
    });
  }
  if (byField.size === 0 && formLevel.length === 0) {
    formLevel.push(otherMessage(body) ?? FALLBACK);
  }
  if (formLevel.length > 0) {
    form.setError(SERVER_ERROR as Path<T>, {
      type: "server",
      message: formLevel.join(" "),
    });
  }
}

/**
 * While `dirty`, the browser asks before the tab closes. Route changes and
 * dialog closes are not caught: the caller awaits the returned function before
 * leaving, and it asks `confirm` only while dirty. It resolves true when
 * leaving is fine.
 */
// ponytail: no router blocking; v0 mounts a BrowserRouter, which has no blocker. Add useBlocker when the app moves to a data router.
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
