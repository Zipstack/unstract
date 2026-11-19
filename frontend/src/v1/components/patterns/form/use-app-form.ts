import { zodResolver } from "@hookform/resolvers/zod";
import { mapFieldErrors, toApiError } from "@v1/services/errors";
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
  const form = useForm<I, unknown, O>({
    resolver: zodResolver(schema),
    defaultValues,
    mode: "onTouched",
    shouldFocusError: true,
  });
  useEffect(() => {
    // react-hook-form re-checks only the field that changed, but a schema rule
    // can put its error on another field (a refine with a path). Re-check every
    // field showing a schema error, so a fixed rule frees Save. Server
    // errors stay until their own field changes or the next submit.
    // A reset's event has no name: it runs before the errors clear, so a
    // re-check then would bring back errors that Discard just dropped.
    const { unsubscribe } = form.watch((_, { name }) => {
      if (name === undefined) {
        return;
      }
      const { root: _root, ...errors } = form.formState.errors;
      const stale = errorLeaves(errors)
        .filter(([path, e]) => path && e.type !== "server")
        .map(([path]) => path as Path<I>);
      if (stale.length > 0) {
        void form.trigger(stale);
      }
    });
    return unsubscribe;
  }, [form]);
  return form;
}

type ErrorLeaf = Readonly<{ type: string; message?: unknown }>;

/** Every field error as [path, error]; a schema refine with no path sits at "". */
export function errorLeaves(node: unknown, path = ""): [string, ErrorLeaf][] {
  if (!node || typeof node !== "object") {
    return [];
  }
  const error = node as { type?: unknown };
  if (typeof error.type === "string") {
    return [[path, node as ErrorLeaf]];
  }
  return Object.entries(node).flatMap(([key, child]) =>
    errorLeaves(child, path ? `${path}.${key}` : key),
  );
}

/** The form-level error key that applyServerErrors sets; FormFooter shows it. */
export const SERVER_ERROR = "root.server";

/** True when a FormField (or any registered control) for `path` is on screen. */
export function isMounted(
  control: Control<FieldValues>,
  path: string,
): boolean {
  // ponytail: reads react-hook-form's field registry; form.test.tsx pins the behaviour across upgrades.
  return get(control._fields, path)?._f?.mount === true;
}

/**
 * Puts each field error of a failed save (anything the v1 client throws) under
 * the field its `attr` names, when that field is on screen, and focuses the
 * first. A dotted attr such as `rows.0.key` is a react-hook-form path.
 * Everything else (non-field errors, attrs with no field shown, a
 * non-validation failure) becomes one form-level message. A cancel sets nothing.
 */
export function applyServerErrors<T extends FieldValues>(
  form: Pick<UseFormReturn<T, unknown, FieldValues>, "control" | "setError">,
  error: unknown,
): void {
  const control = form.control as Control<FieldValues>;
  const shown = Object.keys(toApiError(error).fieldErrors).filter((attr) =>
    isMounted(control, attr),
  );
  const { fields, form: message } = mapFieldErrors(error, shown);
  // Focus the first field the server names, in its order.
  Object.entries(fields).forEach(([attr, text], index) => {
    form.setError(
      attr as Path<T>,
      { type: "server", message: text },
      { shouldFocus: index === 0 },
    );
  });
  if (message !== undefined) {
    form.setError(SERVER_ERROR as Path<T>, { type: "server", message });
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
