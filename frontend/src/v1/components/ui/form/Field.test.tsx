import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ErrorText } from "./ErrorText";
import { Field } from "./Field";
import { Input } from "./Input";
import { Label } from "./Label";
import { PromptTextarea } from "./PromptTextarea";
import { SearchField } from "./SearchField";
import { SecretField } from "./SecretField";
import { Textarea } from "./Textarea";

it.each([
  ["Input", <Input key="c" />],
  ["Textarea", <Textarea key="c" />],
  ["PromptTextarea", <PromptTextarea key="c" />],
  ["SearchField", <SearchField key="c" />],
  ["SecretField", <SecretField key="c" />],
])("associates the Field label with a %s", (_, control) => {
  render(<Field label="Name">{control}</Field>);
  const named = screen.getByLabelText("Name");
  expect(named.dataset.slot).toBe("control");
});

it("associates a standalone Label through htmlFor", () => {
  render(
    <>
      <Label htmlFor="api-key">API key</Label>
      <Input id="api-key" />
    </>,
  );
  expect(screen.getByLabelText("API key").id).toBe("api-key");
});

it("describes the control by its helper text, and adds the error when it appears", () => {
  const { rerender } = render(
    <Field label="Name" helperText="As shown on invoices">
      <Input />
    </Field>,
  );
  const input = screen.getByLabelText("Name");
  const helper = screen.getByText("As shown on invoices");
  expect(input.getAttribute("aria-describedby")).toBe(helper.id);
  expect(input.hasAttribute("aria-invalid")).toBe(false);
  expect(screen.queryByRole("alert")).toBeNull();

  rerender(
    <Field label="Name" helperText="As shown on invoices" error="Required">
      <Input />
    </Field>,
  );
  const alert = screen.getByRole("alert");
  expect(alert.textContent).toBe("Required");
  expect(input.getAttribute("aria-invalid")).toBe("true");
  expect(input.getAttribute("aria-describedby")).toBe(
    `${helper.id} ${alert.id}`,
  );
  expect(
    input.closest("[data-slot=field-frame]")?.hasAttribute("data-invalid"),
  ).toBe(true);
});

it("keeps the control's own description after the field's", () => {
  render(
    <Field label="Name" helperText="Help" id="name">
      <Input aria-describedby="extra" />
    </Field>,
  );
  const input = screen.getByLabelText("Name");
  expect(input.id).toBe("name");
  expect(input.getAttribute("aria-describedby")).toMatch(/ extra$/);
});

it("passes disabled and read-only from the field to the control and frame", () => {
  render(
    <>
      <Field label="Off" disabled>
        <Input />
      </Field>
      <Field label="Fixed" readOnly>
        <Textarea />
      </Field>
    </>,
  );
  const off = screen.getByLabelText("Off") as HTMLInputElement;
  const fixed = screen.getByLabelText("Fixed") as HTMLTextAreaElement;
  expect(off.disabled).toBe(true);
  expect(off.parentElement?.hasAttribute("data-disabled")).toBe(true);
  expect(fixed.readOnly).toBe(true);
  expect(fixed.parentElement?.hasAttribute("data-readonly")).toBe(true);
});

it("renders ErrorText as an alert so it is announced", () => {
  render(<ErrorText>Bad value</ErrorText>);
  expect(screen.getByRole("alert").textContent).toBe("Bad value");
});
