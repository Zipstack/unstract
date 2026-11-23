import { FormField, FormFooter } from "@v1/components/patterns/form";
import { Button, IconButton } from "@v1/components/ui/button";
import { InlineCode } from "@v1/components/ui/code";
import { Input } from "@v1/components/ui/form";
import { ACTION_ICONS, STATUS_ICONS } from "@v1/lib/icons";
import type { ToolSettings } from "@v1/services/promptStudioTool";
import type { JSX } from "react";
import { type Control, useFieldArray, useWatch } from "react-hook-form";
import type { SectionProps } from "./AmbleSection";
import {
  type CustomDataOutput,
  type CustomDataValues,
  customDataFormSchema,
  customDataRows,
  isDefined,
  previewData,
  referencedVariables,
} from "./customData";
import { SettingsSection } from "./SettingsSection";
import { useToolSettingsForm } from "./useToolSettingsForm";

const fromSettings = (s: ToolSettings): CustomDataValues => ({
  rows: customDataRows(s.custom_data),
});

/** Custom Data (frame D13): key-value pairs every prompt can read. */
export function CustomDataSection({
  settings,
  readOnly,
  onDirtyChange,
}: SectionProps): JSX.Element {
  const { form, onSubmit } = useToolSettingsForm({
    settings,
    schema: customDataFormSchema,
    fromSettings,
    onDirtyChange,
  });
  const rows = useFieldArray({ control: form.control, name: "rows" });
  return (
    <SettingsSection
      id="custom-data"
      title="Custom Data"
      description={
        <>
          Key-value pairs sent with every prompt in this project. Use them for
          values the document does not contain — a client code, a region, a
          fiscal year.
        </>
      }
    >
      <form noValidate onSubmit={onSubmit} className="ui:grid ui:gap-3">
        {rows.fields.length > 0 ? (
          <ul className="ui:grid ui:divide-y ui:rounded-lg ui:border ui:bg-card">
            {rows.fields.map((row, index) => (
              <li
                key={row.id}
                className="ui:grid ui:grid-cols-[1fr_2fr_auto] ui:items-start ui:gap-3 ui:p-3"
              >
                <FormField
                  form={form}
                  name={`rows.${index}.key`}
                  label={<span className="ui:sr-only">Key {index + 1}</span>}
                  readOnly={readOnly}
                >
                  {(field) => (
                    <Input
                      {...field}
                      controlClassName="ui:font-mono ui:text-caption"
                    />
                  )}
                </FormField>
                <FormField
                  form={form}
                  name={`rows.${index}.value`}
                  label={<span className="ui:sr-only">Value {index + 1}</span>}
                  readOnly={readOnly}
                >
                  {(field) => (
                    <Input
                      {...field}
                      controlClassName="ui:font-mono ui:text-caption"
                      placeholder="Text, or JSON starting with { or ["
                    />
                  )}
                </FormField>
                {readOnly ? null : (
                  <IconButton
                    size="sm"
                    icon={ACTION_ICONS.delete}
                    aria-label={`Remove pair ${index + 1}`}
                    className="ui:text-destructive"
                    onClick={() => rows.remove(index)}
                  />
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="ui:text-body-small ui:text-muted-foreground">
            No pairs yet.
          </p>
        )}
        {readOnly ? null : (
          <Button
            variant="outline"
            size="lg"
            leadingIcon={ACTION_ICONS.add}
            className="ui:justify-self-end"
            onClick={() => rows.append({ key: "", value: "", json: false })}
          >
            Add pair
          </Button>
        )}
        <ReferencedVariables
          prompts={settings.prompts}
          control={form.control}
        />
        {readOnly ? null : <FormFooter form={form} />}
      </form>
    </SettingsSection>
  );
}

/** Which `{{custom_data.…}}` paths active prompts use, and whether the unsaved pairs define them. */
function ReferencedVariables({
  prompts,
  control,
}: Readonly<{
  prompts: ToolSettings["prompts"];
  control: Control<CustomDataValues, unknown, CustomDataOutput>;
}>): JSX.Element | null {
  const rows = useWatch({ control, name: "rows" });
  const paths = referencedVariables(prompts);
  if (paths.length === 0) {
    return (
      <p className="ui:text-body-small ui:text-muted-foreground">
        No active prompt uses custom data yet. Add a variable such as{" "}
        <InlineCode variant="plain">{"{{custom_data.your_key}}"}</InlineCode> to
        a prompt to use a pair.
      </p>
    );
  }
  const data = previewData(rows);
  const missing = paths.filter((p) => !isDefined(data, p)).length;
  return (
    <div className="ui:grid ui:gap-2 ui:rounded-lg ui:border ui:p-3">
      <h3 className="ui:text-body-small ui:font-semibold ui:text-foreground">
        Used in active prompts
        {missing > 0 ? ` · ${missing} not defined` : null}
      </h3>
      <ul className="ui:grid ui:gap-1">
        {paths.map((path) => {
          const defined = isDefined(data, path);
          const Icon = defined ? STATUS_ICONS.success : STATUS_ICONS.warning;
          return (
            <li
              key={path}
              className="ui:flex ui:items-center ui:gap-2 ui:text-body-small"
            >
              <Icon
                aria-hidden
                className={
                  defined
                    ? "ui:size-4 ui:text-success"
                    : "ui:size-4 ui:text-warning"
                }
              />
              <InlineCode variant="plain">{`custom_data.${path}`}</InlineCode>
              <span className="ui:text-muted-foreground">
                {defined ? "defined" : "not defined"}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
