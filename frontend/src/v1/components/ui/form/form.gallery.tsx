import { Search } from "lucide-react";
import type { ReactElement } from "react";
import { Field } from "./Field";
import { Input } from "./Input";
import { PromptTextarea } from "./PromptTextarea";
import { SearchField } from "./SearchField";
import { SecretField } from "./SecretField";
import { Textarea } from "./Textarea";

/*
 * Every variant and state of the text inputs, for the component gallery
 * (P1-T01, not merged yet: register these there, where each entry is shown in
 * Light, Dark and Unstract). Until then markup.test.tsx renders each one,
 * snapshots its markup and runs axe on it. Hover and focus are CSS-only
 * (`hover:` and `has-[...:focus-visible]` classes), so they show in the
 * gallery, not here; the snapshot pins the classes that draw them.
 */

export type GalleryEntry = Readonly<{ name: string; element: ReactElement }>;

export const FORM_GALLERY: readonly GalleryEntry[] = [
  {
    name: "Input, default",
    element: (
      <Field id="g-default" label="Name">
        <Input placeholder="Acme invoices" />
      </Field>
    ),
  },
  {
    name: "Input with adornments",
    element: (
      <Field id="g-adorned" label="Site">
        <Input
          leading={<Search aria-hidden />}
          prefix="https://"
          suffix=".com"
        />
      </Field>
    ),
  },
  {
    name: "Input, invalid with error",
    element: (
      <Field id="g-invalid" label="Name" error="Enter a name">
        <Input />
      </Field>
    ),
  },
  {
    name: "Input, disabled",
    element: (
      <Field id="g-disabled" label="Name" disabled>
        <Input defaultValue="Acme" />
      </Field>
    ),
  },
  {
    name: "Input, read-only",
    element: (
      <Field id="g-readonly" label="Name" readOnly>
        <Input value="Acme" />
      </Field>
    ),
  },
  {
    name: "Field with helper and error",
    element: (
      <Field
        id="g-helper"
        label="Webhook URL"
        helperText="We post each result here."
        error="Enter a URL"
      >
        <Input />
      </Field>
    ),
  },
  {
    name: "Textarea",
    element: (
      <Field id="g-textarea" label="Notes">
        <Textarea />
      </Field>
    ),
  },
  {
    name: "Prompt textarea",
    element: (
      <Field id="g-prompt" label="Prompt">
        <PromptTextarea />
      </Field>
    ),
  },
  {
    name: "Search field with a value",
    element: (
      <Field id="g-search" label="Search">
        <SearchField defaultValue="invoices" />
      </Field>
    ),
  },
  {
    name: "Secret field, read-only",
    element: (
      <Field id="g-secret" label="API key" readOnly>
        <SecretField value="sk-test-1234" />
      </Field>
    ),
  },
];
