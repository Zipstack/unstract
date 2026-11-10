// TEST BRANCH ONLY (UN-4257-fev1-lane-b-test): a page to see Lane B's v1
// pieces against a real backend before the v1 shell (P2-T01) exists.
// Never merged; delete when the shell renders these components.
import { ThemeProvider } from "@v1/app/theme/ThemeProvider";
import {
  applyServerErrors,
  FormField,
  FormFooter,
  type ServerErrorBody,
  useAppForm,
} from "@v1/components/patterns/form";
import {
  Field,
  Input,
  PromptTextarea,
  SearchField,
  SecretField,
  Textarea,
} from "@v1/components/ui/form";
import { PluginProvider, Slot } from "@v1/lib/plugins";
import { PluginSlot } from "@v1/plugins";
import { AccountMenu } from "@v1/shell/AccountMenu";
import { OrganizationSwitcher } from "@v1/shell/OrganizationSwitcher";
import { useState } from "react";
import { z } from "zod";

export interface V1PreviewProps {
  user: { name: string; email: string };
  organization: { id: string; name: string; displayName: string };
}

const schema = z.object({
  name: z.string().min(1, "Enter a name"),
  url: z.string().url("Enter a URL"),
  description: z.string().max(40, "At most 40 characters"),
});
type Values = z.infer<typeof schema>;

// Fake save: "taken" gets a field error, "boom" a form-level one, as the backend sends them.
async function fakeSave(values: Values): Promise<ServerErrorBody | undefined> {
  await new Promise((resolve) => setTimeout(resolve, 600));
  if (values.name === "taken") {
    return {
      type: "validation_error",
      errors: [{ code: "unique", detail: "That name is taken", attr: "name" }],
    };
  }
  if (values.name === "boom") {
    return {
      type: "server_error",
      errors: [{ code: "error", detail: "The server failed", attr: null }],
    };
  }
  return undefined;
}

function SampleForm() {
  const form = useAppForm({
    schema,
    defaultValues: {
      name: "demo",
      url: "https://example.com",
      description: "",
    },
  });
  return (
    <form
      aria-label="Sample form"
      className="ui:grid ui:gap-4"
      onSubmit={form.handleSubmit(async (values) => {
        const error = await fakeSave(values);
        if (error === undefined) {
          form.reset(values);
        } else {
          applyServerErrors(form, error);
        }
      })}
    >
      <FormField
        form={form}
        name="name"
        label="Name"
        helperText='Try "taken" or "boom"'
      >
        {(field) => <Input {...field} />}
      </FormField>
      <FormField form={form} name="url" label="URL">
        {(field) => <Input {...field} />}
      </FormField>
      <FormField form={form} name="description" label="Description">
        {(field) => <Textarea {...field} />}
      </FormField>
      <FormFooter form={form} />
    </form>
  );
}

function Inputs() {
  const [search, setSearch] = useState("");
  const [copy, setCopy] = useState("");
  const [sent, setSent] = useState("");
  return (
    <div className="ui:grid ui:gap-4">
      <Field label="Plain input" helperText="Helper text">
        <Input placeholder="Type here" />
      </Field>
      <Field label="Invalid input" error="Something is wrong">
        <Input defaultValue="bad value" />
      </Field>
      <Field label="Disabled input" disabled>
        <Input defaultValue="disabled" />
      </Field>
      <Field label="Read-only input" readOnly>
        <Input defaultValue="read only" />
      </Field>
      <Field label="Search">
        <SearchField
          value={search}
          onValueChange={setSearch}
          placeholder="Search"
        />
      </Field>
      <p
        className="ui:text-caption ui:text-muted-foreground"
        data-testid="search-value"
      >
        search: {search}
      </p>
      <Field label="API key" readOnly>
        <SecretField
          readOnly
          defaultValue="sk-test-1234567890"
          onCopyResult={(result) => setCopy(result.status)}
        />
      </Field>
      <p
        className="ui:text-caption ui:text-muted-foreground"
        data-testid="copy-result"
      >
        copy: {copy}
      </p>
      <Field label="Prompt">
        <PromptTextarea placeholder="Ask something" onSubmit={setSent} />
      </Field>
      <p
        className="ui:text-caption ui:text-muted-foreground"
        data-testid="prompt-sent"
      >
        sent: {sent}
      </p>
    </div>
  );
}

export function V1Preview({ user, organization }: V1PreviewProps) {
  return (
    <ThemeProvider className="ui:min-h-screen ui:bg-background ui:text-foreground">
      <PluginProvider slot={PluginSlot}>
        <header className="ui:flex ui:h-14 ui:items-center ui:justify-between ui:border-b ui:border-border ui:bg-sidebar ui:px-3">
          <div className="ui:flex ui:items-center ui:gap-3">
            <span className="ui:text-sm ui:font-semibold ui:text-sidebar-foreground">
              v1 preview · test branch only
            </span>
            {/* Cloud fills this with the product switcher (P2-T13). */}
            <Slot id="shell.product-switcher" props={{}} fallback={null} />
          </div>
          <div className="ui:flex ui:items-center ui:gap-1.5">
            <OrganizationSwitcher current={organization} />
            <AccountMenu
              user={user}
              profileHref={`/${organization.name}/profile`}
            />
          </div>
        </header>
        <main className="ui:grid ui:max-w-5xl ui:gap-8 ui:p-6 ui:md:grid-cols-2">
          <section
            aria-label="Text inputs"
            className="ui:grid ui:content-start ui:gap-3"
          >
            <h2 className="ui:text-sm ui:font-semibold">
              Text inputs (P1-T03)
            </h2>
            <Inputs />
          </section>
          <section
            aria-label="Form system"
            className="ui:grid ui:content-start ui:gap-3"
          >
            <h2 className="ui:text-sm ui:font-semibold">
              Form system (P1-T06)
            </h2>
            <SampleForm />
          </section>
        </main>
      </PluginProvider>
    </ThemeProvider>
  );
}
