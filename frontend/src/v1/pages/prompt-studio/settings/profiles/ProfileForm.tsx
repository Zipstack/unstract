import { useMutation, useQuery } from "@tanstack/react-query";
import {
  applyServerErrors,
  FormField,
  SERVER_ERROR,
  useAppForm,
} from "@v1/components/patterns/form";
import { Button } from "@v1/components/ui/button";
import { ErrorText, Input } from "@v1/components/ui/form";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@v1/components/ui/navigation";
import { Switch } from "@v1/components/ui/toggles";
import { toast } from "@v1/lib/notify";
import { SelectField } from "@v1/pages/prompt-studio/settings/standins";
import {
  createProfile,
  type LlmProfile,
  promptProfileQueries,
  RETRIEVAL_STRATEGIES,
  updateProfile,
} from "@v1/services/promptProfiles";
import { type JSX, useEffect, useId, useState } from "react";
import { get, useFormState, useWatch } from "react-hook-form";
import { AdapterPicker, type AdapterPickerProps } from "./AdapterPicker";
import {
  approxTokens,
  NEW_PROFILE,
  type ProfileFormOutput,
  type ProfileFormValues,
  profileFormSchema,
  profileValues,
  toProfileBody,
} from "./profileForm";

const ADAPTER_FIELDS = [
  { name: "llm", label: "LLM", type: "LLM", placeholder: "Select an LLM" },
  {
    name: "embedding_model",
    label: "Embedding Model",
    type: "EMBEDDING",
    placeholder: "Select an embedding model",
  },
  {
    name: "vector_store",
    label: "Vector Database",
    type: "VECTOR_DB",
    placeholder: "Select a vector database",
  },
  {
    name: "x2text",
    label: "Text Extractor",
    type: "X2TEXT",
    placeholder: "Select a text extractor",
  },
] as const satisfies readonly {
  name: keyof ProfileFormValues;
  label: string;
  type: AdapterPickerProps["adapterType"];
  placeholder: string;
}[];

const ADVANCED_FIELDS = [
  "retrieval_strategy",
  "similarity_top_k",
  "section",
] as const;

/** Model titles, until the backend's strategy list loads. */
const STRATEGY_TITLES: Record<(typeof RETRIEVAL_STRATEGIES)[number], string> = {
  simple: "Simple retrieval",
  subquestion: "Subquestion retrieval",
  fusion: "Fusion retrieval",
  recursive: "Recursive retrieval",
  router: "Router retrieval",
  keyword_table: "Keyword table retrieval",
  automerging: "Auto-merging retrieval",
};

export type ProfileFormProps = Readonly<{
  toolId: string;
  /** The profile being edited; omitted to add one. */
  profile?: LlmProfile;
  /** Other profiles' names in this project. */
  takenNames: readonly string[];
  onSaved: (profile: LlmProfile) => void;
  onCancel: () => void;
  onDirtyChange: (dirty: boolean) => void;
}>;

/** Add New LLM Profile / Edit LLM Profile (frame D10, with v0's other fields). */
export function ProfileForm({
  toolId,
  profile,
  takenNames,
  onSaved,
  onCancel,
  onDirtyChange,
}: ProfileFormProps): JSX.Element {
  const form = useAppForm<ProfileFormValues, ProfileFormOutput>({
    schema: profileFormSchema(takenNames),
    defaultValues: profile ? profileValues(profile) : NEW_PROFILE,
  });
  const dirty = form.formState.isDirty;
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  // A closed form has nothing left to lose.
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  const save = useMutation({
    mutationFn: (values: ProfileFormOutput) => {
      const body = toProfileBody(values, toolId);
      return profile
        ? updateProfile(profile.profile_id, body)
        : createProfile(body);
    },
    meta: { notify: false },
  });
  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const saved = await save.mutateAsync(values);
      if (saved.vision_warning) {
        toast.warning("Saved — check LLM compatibility", {
          description: saved.vision_warning,
        });
      } else {
        toast.success("Profile saved");
      }
      onSaved(saved);
    } catch (error) {
      applyServerErrors(form, error);
    }
  });
  const { errors, isSubmitting } = useFormState({ control: form.control });
  const advancedError = ADVANCED_FIELDS.some((f) => get(errors, f));
  const [advancedOpen, setAdvancedOpen] = useState(profile !== undefined);
  const formError = get(errors, SERVER_ERROR)?.message;

  return (
    <form noValidate onSubmit={onSubmit} className="ui:grid ui:gap-4">
      <FormField form={form} name="profile_name" label="Name">
        {(field) => <Input {...field} placeholder="e.g. production-claude" />}
      </FormField>
      {ADAPTER_FIELDS.map((a) => (
        <FormField key={a.name} form={form} name={a.name} label={a.label}>
          {(field) => (
            <AdapterPicker
              adapterType={a.type}
              name={field.name}
              value={field.value as string}
              onChange={field.onChange}
              onBlur={field.onBlur}
              placeholder={a.placeholder}
              currentName={profile?.[a.name]}
            />
          )}
        </FormField>
      ))}
      <div className="ui:grid ui:grid-cols-2 ui:gap-4">
        <ChunkSizeField form={form} />
        <FormField form={form} name="chunk_overlap" label="Chunk overlap">
          {(field) => <Input {...field} inputMode="numeric" />}
        </FormField>
      </div>
      <ReindexSwitch form={form} />
      <Collapsible
        open={advancedOpen || advancedError}
        onOpenChange={setAdvancedOpen}
        className="ui:grid ui:gap-3"
      >
        <CollapsibleTrigger className="ui:justify-self-start">
          Advanced settings
        </CollapsibleTrigger>
        <CollapsibleContent className="ui:grid ui:gap-4">
          <StrategyField form={form} toolId={toolId} />
          <div className="ui:grid ui:grid-cols-2 ui:gap-4">
            <FormField
              form={form}
              name="similarity_top_k"
              label="Matching count limit"
              helperText="How many of the best-matching chunks a prompt reads (top-k)."
            >
              {(field) => <Input {...field} inputMode="numeric" />}
            </FormField>
            <FormField form={form} name="section" label="Limit to section">
              {(field) => (
                <SelectField
                  name={field.name}
                  value={field.value}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                  placeholder="No limit"
                  options={[{ value: "Default", label: "Default" }]}
                />
              )}
            </FormField>
          </div>
        </CollapsibleContent>
      </Collapsible>
      {formError ? <ErrorText>{formError}</ErrorText> : null}
      <div className="ui:flex ui:justify-end ui:gap-2">
        <Button size="lg" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          size="lg"
          type="submit"
          loading={isSubmitting}
          data-testid="ps-profile-save"
        >
          Save profile
        </Button>
      </div>
    </form>
  );
}

type Form = ReturnType<typeof useAppForm<ProfileFormValues, ProfileFormOutput>>;

/** Chunk size with v0's estimate: about how many tokens a chunk is, and the LLM's context window. */
function ChunkSizeField({ form }: Readonly<{ form: Form }>): JSX.Element {
  const [llm, size] = useWatch({
    control: form.control,
    name: ["llm", "chunk_size"],
  });
  const info = useQuery({
    ...promptProfileQueries.adapterInfo(llm),
    enabled: llm !== "",
  });
  const chars = Number(size);
  const estimate = Number.isFinite(chars)
    ? `≈ ${approxTokens(chars)} tokens`
    : "";
  const max = info.data ? `, LLM context ${info.data.context_window_size}` : "";
  return (
    <FormField
      form={form}
      name="chunk_size"
      label="Chunk size"
      helperText={`Set to 0 if documents are small. ${estimate}${max}`.trim()}
    >
      {(field) => <Input {...field} inputMode="numeric" />}
    </FormField>
  );
}

/** Frame D10's row: label and help on the left, the switch on the right. */
function ReindexSwitch({ form }: Readonly<{ form: Form }>): JSX.Element {
  const on = useWatch({ control: form.control, name: "reindex" });
  const id = useId();
  return (
    <div className="ui:flex ui:items-start ui:justify-between ui:gap-4 ui:rounded-lg ui:border ui:bg-card ui:px-4 ui:py-3.5">
      <div className="ui:grid ui:gap-0.5">
        <p
          id={`${id}-label`}
          className="ui:text-body-small ui:font-semibold ui:text-foreground"
        >
          Reindex on save
        </p>
        <p
          id={`${id}-help`}
          className="ui:text-caption ui:text-muted-foreground"
        >
          Deployed runs index each document again instead of reusing its stored
          index. Slower; use it after changing chunk size.
        </p>
      </div>
      <Switch
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-help`}
        checked={on}
        onCheckedChange={(checked) =>
          form.setValue("reindex", checked, { shouldDirty: true })
        }
      />
    </div>
  );
}

function StrategyField({
  form,
  toolId,
}: Readonly<{ form: Form; toolId: string }>): JSX.Element {
  const strategies = useQuery(promptProfileQueries.strategies(toolId));
  const chosen = useWatch({
    control: form.control,
    name: "retrieval_strategy",
  });
  const info = strategies.data?.find((s) => s.key === chosen);
  const titles = new Map(strategies.data?.map((s) => [s.key, s.title]));
  return (
    <FormField
      form={form}
      name="retrieval_strategy"
      label="Retrieval strategy"
      helperText={
        info
          ? `${info.description} Token usage: ${info.token_usage}. Cost: ${info.cost_impact}.`
          : undefined
      }
    >
      {(field) => (
        <SelectField
          name={field.name}
          value={field.value}
          onChange={field.onChange}
          onBlur={field.onBlur}
          placeholder="Select a retrieval strategy"
          options={RETRIEVAL_STRATEGIES.map((key) => ({
            value: key,
            label: titles.get(key) ?? STRATEGY_TITLES[key],
          }))}
        />
      )}
    </FormField>
  );
}
