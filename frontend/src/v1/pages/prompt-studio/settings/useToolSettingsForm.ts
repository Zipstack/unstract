import { useMutation, useQueryClient } from "@tanstack/react-query";
import { applyServerErrors, useAppForm } from "@v1/components/patterns/form";
import {
  promptStudioToolKeys,
  type ToolSettings,
  type ToolSettingsPatch,
  updateToolSettings,
} from "@v1/services/promptStudioTool";
import { type FormEvent, useEffect } from "react";
import type {
  DefaultValues,
  FieldValues,
  Path,
  PathValue,
  UseFormReturn,
} from "react-hook-form";
import type { z } from "zod";

export type ToolSettingsFormOptions<
  I extends FieldValues,
  O extends ToolSettingsPatch,
> = Readonly<{
  settings: ToolSettings;
  schema: z.ZodType<O, I>;
  /** The saved settings as this section's form values. */
  fromSettings: (settings: ToolSettings) => I;
  onDirtyChange: (dirty: boolean) => void;
}>;

/**
 * The patch to send: the schema's output without the form fields the user did
 * not change. An output key that is not a form field (custom data, grammar)
 * is the whole section's value and always goes.
 */
function changedOnly<O extends ToolSettingsPatch>(
  values: O,
  fields: object,
  dirtyFields: Partial<Record<string, unknown>>,
): ToolSettingsPatch {
  return Object.fromEntries(
    Object.entries(values).filter(
      ([key]) => !(key in fields) || dirtyFields[key] !== undefined,
    ),
  );
}

/** Puts back the fields typed while the save ran, as unsaved changes. */
function keepTypedSince<I extends FieldValues, O>(
  form: UseFormReturn<I, unknown, O>,
  submitted: I,
  current: I,
): void {
  for (const name of Object.keys(current) as Path<I>[]) {
    const now = form.getValues(name);
    const typed = current[name as keyof I];
    const changed = (a: unknown, b: unknown) =>
      JSON.stringify(a) !== JSON.stringify(b);
    if (changed(typed, submitted[name as keyof I]) && changed(typed, now)) {
      form.setValue(name, typed as PathValue<I, Path<I>>, {
        shouldDirty: true,
      });
    }
  }
}

/**
 * One project-settings section as its own form. The schema's output is the
 * patch, so saving sends only this section's changed fields
 * (`PATCH prompt-studio/{id}/`), refreshes the cached project and makes the
 * saved values the new baseline; anything typed while the save runs stays.
 * Settings that change elsewhere replace the form's values whenever it has no
 * unsaved changes.
 */
export function useToolSettingsForm<
  I extends FieldValues,
  O extends ToolSettingsPatch,
>({
  settings,
  schema,
  fromSettings,
  onDirtyChange,
}: ToolSettingsFormOptions<I, O>): Readonly<{
  form: UseFormReturn<I, unknown, O>;
  onSubmit: (event?: FormEvent) => Promise<void>;
}> {
  const queryClient = useQueryClient();
  const saved = fromSettings(settings);
  const form = useAppForm<I, O>({
    schema,
    defaultValues: saved as DefaultValues<I>,
  });
  const dirty = form.formState.isDirty;
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  // A section that goes away has nothing left to lose.
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);

  // Compared by content: `saved` is a new object on every render.
  const savedKey = JSON.stringify(saved);
  useEffect(() => {
    if (!dirty) {
      form.reset(JSON.parse(savedKey) as I);
    }
  }, [savedKey, dirty, form]);

  const save = useMutation({
    mutationFn: (patch: ToolSettingsPatch) =>
      updateToolSettings(settings.tool_id, patch),
    // The form shows the failure; the query client only logs it.
    meta: { notify: false },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    const key = promptStudioToolKeys.detail(settings.tool_id);
    const submitted = form.getValues();
    try {
      const patch = changedOnly(
        values,
        form.formState.defaultValues ?? {},
        form.formState.dirtyFields,
      );
      const next = await save.mutateAsync(patch);
      // A read that started before the save would land older data on top.
      await queryClient.cancelQueries({ queryKey: key });
      queryClient.setQueryData(key, next);
      const current = form.getValues();
      form.reset(fromSettings(next));
      keepTypedSince(form, submitted, current);
    } catch (error) {
      applyServerErrors(form, error);
    }
  });
  return { form, onSubmit };
}
