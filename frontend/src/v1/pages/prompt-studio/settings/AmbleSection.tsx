import { FormField, FormFooter } from "@v1/components/patterns/form";
import { Button } from "@v1/components/ui/button";
import { Textarea } from "@v1/components/ui/form";
import type { ToolSettings } from "@v1/services/promptStudioTool";
import type { JSX } from "react";
import { z } from "zod";
import { SettingsSection } from "./SettingsSection";
import { anchorId } from "./sections";
import { useToolSettingsForm } from "./useToolSettingsForm";

/** The texts a new project ships with (v0 DefaultPrompts.json); Reset puts them back. */
export const DEFAULT_PREAMBLE =
  "Your ability to extract and summarize this context accurately is essential for effective analysis. Pay close attention to the context's language, structure, and any cross-references to ensure a comprehensive and precise extraction of information. Do not use prior knowledge or information from outside the context to answer the questions. Only use the information provided in the context to answer the questions.";
export const DEFAULT_POSTAMBLE =
  "Do not include any explanation in the reply. Only include the extracted information in the reply.";

const schema = z.object({ preamble: z.string(), postamble: z.string() });
type Values = z.infer<typeof schema>;

const fromSettings = (s: ToolSettings): Values => ({
  preamble: s.preamble ?? "",
  postamble: s.postamble ?? "",
});

const FIELDS = [
  {
    name: "preamble",
    label: "Preamble",
    helper:
      "Prepended to every prompt in this project, before the prompt text.",
    fallback: DEFAULT_PREAMBLE,
  },
  {
    name: "postamble",
    label: "Postamble",
    helper: "Appended to every prompt in this project, after the prompt text.",
    fallback: DEFAULT_POSTAMBLE,
  },
] as const;

export type SectionProps = Readonly<{
  settings: ToolSettings;
  readOnly: boolean;
  onDirtyChange: (dirty: boolean) => void;
}>;

/** Preamble and Postamble (frame D15): one form, two texts. */
export function AmbleSection({
  settings,
  readOnly,
  onDirtyChange,
}: SectionProps): JSX.Element {
  const { form, onSubmit } = useToolSettingsForm({
    settings,
    schema,
    fromSettings,
    onDirtyChange,
  });
  return (
    <SettingsSection id="preamble" title="Preamble">
      <form noValidate onSubmit={onSubmit} className="ui:grid ui:gap-4">
        {FIELDS.map((f) => (
          <div key={f.name} id={anchorId(f.name)} className="ui:scroll-mt-4">
            <FormField
              form={form}
              name={f.name}
              label={f.label}
              helperText={f.helper}
              readOnly={readOnly}
            >
              {(field) => (
                <Textarea {...field} rows={4} data-testid={`ps-${f.name}`} />
              )}
            </FormField>
            {readOnly ? null : (
              <Button
                variant="link"
                size="xs"
                onClick={() =>
                  form.setValue(f.name, f.fallback, { shouldDirty: true })
                }
              >
                Reset {f.label.toLowerCase()} to the default
              </Button>
            )}
          </div>
        ))}
        {readOnly ? null : <FormFooter form={form} />}
      </form>
    </SettingsSection>
  );
}
