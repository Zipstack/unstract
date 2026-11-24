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
 * One project-settings section as its own form. The schema's output is the
 * patch, so saving sends only this section's fields
 * (`PATCH prompt-studio/{id}/`), refreshes the cached project and makes the
 * saved values the new baseline. Settings that change elsewhere replace the
 * form's values while it has no unsaved changes.
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
    if (!form.formState.isDirty) {
      form.reset(JSON.parse(savedKey) as I);
    }
  }, [savedKey, form]);

  const save = useMutation({
    mutationFn: (patch: ToolSettingsPatch) =>
      updateToolSettings(settings.tool_id, patch),
    // The form shows the failure; the query client only logs it.
    meta: { notify: false },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const next = await save.mutateAsync(values);
      queryClient.setQueryData(
        promptStudioToolKeys.detail(settings.tool_id),
        next,
      );
      form.reset(fromSettings(next));
    } catch (error) {
      applyServerErrors(form, error);
    }
  });
  return { form, onSubmit };
}
