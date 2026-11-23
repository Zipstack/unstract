import { FormField, FormFooter } from "@v1/components/patterns/form";
import { Button, IconButton } from "@v1/components/ui/button";
import { Input } from "@v1/components/ui/form";
import { ACTION_ICONS } from "@v1/lib/icons";
import type { ToolSettings } from "@v1/services/promptStudioTool";
import { ChevronRight } from "lucide-react";
import type { JSX } from "react";
import { useFieldArray } from "react-hook-form";
import type { SectionProps } from "./AmbleSection";
import {
  GRAMMAR_LIMIT,
  type GrammarValues,
  grammarFormSchema,
  grammarRows,
} from "./grammar";
import { SettingsSection } from "./SettingsSection";
import { useToolSettingsForm } from "./useToolSettingsForm";

const fromSettings = (s: ToolSettings): GrammarValues => ({
  rows: grammarRows(s.prompt_grammer),
});

/** Grammar (frame D14): words and the phrases treated as equal to them. */
export function GrammarSection({
  settings,
  readOnly,
  onDirtyChange,
}: SectionProps): JSX.Element {
  const { form, onSubmit } = useToolSettingsForm({
    settings,
    schema: grammarFormSchema,
    fromSettings,
    onDirtyChange,
  });
  const rows = useFieldArray({ control: form.control, name: "rows" });
  const full = rows.fields.length >= GRAMMAR_LIMIT;
  return (
    <SettingsSection
      id="grammar"
      title="Grammar"
      description="Words and phrases the extractor should treat as equivalent. Applied before a prompt sees the document text."
    >
      <form noValidate onSubmit={onSubmit} className="ui:grid ui:gap-3">
        {rows.fields.length > 0 ? (
          <ul className="ui:grid ui:divide-y ui:rounded-lg ui:border ui:bg-card">
            {rows.fields.map((row, index) => (
              <li
                key={row.id}
                className="ui:grid ui:grid-cols-[1fr_auto_2fr_auto] ui:items-start ui:gap-3 ui:p-3"
              >
                <FormField
                  form={form}
                  name={`rows.${index}.word`}
                  label={<span className="ui:sr-only">Word {index + 1}</span>}
                  readOnly={readOnly}
                >
                  {(field) => (
                    <Input
                      {...field}
                      controlClassName="ui:font-mono ui:text-caption"
                    />
                  )}
                </FormField>
                <ChevronRight
                  aria-hidden
                  className="ui:mt-2 ui:size-3.5 ui:text-muted-foreground"
                />
                <FormField
                  form={form}
                  name={`rows.${index}.synonyms`}
                  label={
                    <span className="ui:sr-only">
                      Equivalents of word {index + 1}, comma-separated
                    </span>
                  }
                  readOnly={readOnly}
                >
                  {/* ponytail: comma-separated text until P1-T04's MultiSelect takes typed values as chips (frame D14). */}
                  {(field) => (
                    <Input
                      {...field}
                      controlClassName="ui:text-caption"
                      placeholder="Comma-separated equivalents"
                    />
                  )}
                </FormField>
                {readOnly ? null : (
                  <IconButton
                    size="sm"
                    icon={ACTION_ICONS.delete}
                    aria-label={`Remove word ${index + 1}`}
                    className="ui:text-destructive"
                    onClick={() => rows.remove(index)}
                  />
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="ui:text-body-small ui:text-muted-foreground">
            No words yet.
          </p>
        )}
        {readOnly ? null : (
          <Button
            variant="outline"
            size="lg"
            leadingIcon={ACTION_ICONS.add}
            className="ui:justify-self-end"
            disabled={full}
            title={full ? `Up to ${GRAMMAR_LIMIT} words` : undefined}
            onClick={() => rows.append({ word: "", synonyms: "" })}
          >
            Add synonym
          </Button>
        )}
        {readOnly ? null : <FormFooter form={form} />}
      </form>
    </SettingsSection>
  );
}
