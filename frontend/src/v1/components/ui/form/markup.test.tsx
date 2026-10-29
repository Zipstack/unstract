import { render } from "@testing-library/react";
import { Search } from "lucide-react";
import type { ReactElement } from "react";
import { expect, it } from "vitest";
import { Field } from "./Field";
import { Input } from "./Input";
import { PromptTextarea } from "./PromptTextarea";
import { SearchField } from "./SearchField";
import { SecretField } from "./SecretField";
import { Textarea } from "./Textarea";

// One snapshot per variant and state, so a markup or class change shows in review.
const VARIANTS: [string, ReactElement][] = [
  ["input", <Input key="v" aria-label="Name" placeholder="Name" />],
  [
    "input with adornments",
    <Input
      key="v"
      aria-label="Site"
      leading={<Search aria-hidden />}
      prefix="https://"
      suffix=".com"
    />,
  ],
  ["input invalid", <Input key="v" aria-label="Name" invalid />],
  ["input disabled", <Input key="v" aria-label="Name" disabled />],
  ["input read-only", <Input key="v" aria-label="Name" readOnly value="x" />],
  ["textarea", <Textarea key="v" aria-label="Notes" />],
  ["prompt textarea", <PromptTextarea key="v" aria-label="Prompt" />],
  [
    "search field",
    <SearchField key="v" aria-label="Search" defaultValue="q" />,
  ],
  [
    "secret field",
    <SecretField
      key="v"
      aria-label="Key"
      defaultValue="sk"
      onCopyResult={() => undefined}
    />,
  ],
  [
    "field with helper and error",
    <Field key="v" id="f" label="Name" helperText="Help" error="Required">
      <Input />
    </Field>,
  ],
];

it.each(VARIANTS)("renders the %s markup", (_, element) => {
  const { container } = render(element);
  expect(container.innerHTML).toMatchSnapshot();
});
