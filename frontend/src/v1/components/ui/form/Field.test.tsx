import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import type { JSX } from "react";
import { expect, it } from "vitest";
import { ErrorText } from "./ErrorText";
import { Field } from "./Field";
import { fieldFrameVariants } from "./FieldFrame";
import { useFieldControl } from "./field-context";
import { Input } from "./Input";
import { Label } from "./Label";
import { PromptTextarea } from "./PromptTextarea";
import { SearchField } from "./SearchField";
import { SecretField } from "./SecretField";
import { Textarea } from "./Textarea";

/** Every text control, rendered with the given props. */
const CONTROLS: [string, (props: ControlProps) => JSX.Element][] = [
  ["Input", (p) => <Input {...p} />],
  ["Textarea", (p) => <Textarea {...p} />],
  ["PromptTextarea", (p) => <PromptTextarea {...p} />],
  ["SearchField", (p) => <SearchField {...p} />],
  ["SecretField", (p) => <SecretField {...p} />],
];

type ControlProps = Readonly<{
  invalid?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  "aria-label"?: string;
}>;

const frameOf = (control: HTMLElement) =>
  control.closest("[data-slot=field-frame]") as HTMLElement;

it.each(CONTROLS)("associates the Field label with a %s", (_, make) => {
  renderV1(<Field label="Name">{make({})}</Field>);
  const named = screen.getByLabelText("Name");
  expect(named.dataset.slot).toBe("control");
});

it.each(
  CONTROLS,
)("wires a %s to the Field's error, helper and states", (_, make) => {
  renderV1(
    <Field label="Name" id="name" helperText="Help" error="Bad" disabled>
      {make({})}
    </Field>,
  );
  const control = screen.getByLabelText("Name") as HTMLInputElement;
  expect(control.getAttribute("aria-invalid")).toBe("true");
  expect(control.getAttribute("aria-describedby")).toBe(
    "name-helper name-error",
  );
  expect(control.disabled).toBe(true);
  expect(frameOf(control).hasAttribute("data-invalid")).toBe(true);
  expect(frameOf(control).hasAttribute("data-disabled")).toBe(true);
});

it.each(
  CONTROLS,
)("marks a standalone %s from its own state props", (_, make) => {
  const { rerender } = renderV1(make({ "aria-label": "C" }));
  const control = () => screen.getByLabelText("C") as HTMLInputElement;
  expect(control().hasAttribute("aria-invalid")).toBe(false);
  for (const flag of ["data-invalid", "data-disabled", "data-readonly"]) {
    expect(frameOf(control()).hasAttribute(flag)).toBe(false);
  }
  rerender(make({ "aria-label": "C", invalid: true, readOnly: true }));
  expect(control().getAttribute("aria-invalid")).toBe("true");
  expect(control().readOnly).toBe(true);
  expect(frameOf(control()).hasAttribute("data-invalid")).toBe(true);
  expect(frameOf(control()).hasAttribute("data-readonly")).toBe(true);
  rerender(make({ "aria-label": "C", disabled: true }));
  expect(control().disabled).toBe(true);
  expect(frameOf(control()).hasAttribute("data-disabled")).toBe(true);
});

it.each([
  ["Input", <Input key="i" id="own" />],
  ["Textarea", <Textarea key="t" id="own" />],
])("names a %s that has its own id: the Field's id wins", (_, control) => {
  renderV1(<Field label="Name">{control}</Field>);
  const named = screen.getByLabelText("Name");
  expect(named.id).not.toBe("own");
  expect(document.querySelector("label")?.htmlFor).toBe(named.id);
});

it("associates a standalone Label through htmlFor", () => {
  renderV1(
    <>
      <Label htmlFor="api-key">API key</Label>
      <Input id="api-key" />
    </>,
  );
  expect(screen.getByLabelText("API key").id).toBe("api-key");
});

it("describes the control by its helper text, and adds the error when it appears", () => {
  const { rerender } = renderV1(
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
  renderV1(
    <Field label="Name" helperText="Help" id="name">
      <Input aria-describedby="extra" />
    </Field>,
  );
  const input = screen.getByLabelText("Name");
  expect(input.id).toBe("name");
  expect(input.getAttribute("aria-describedby")).toMatch(/ extra$/);
});

it("passes disabled and read-only from the field to the control and frame", () => {
  renderV1(
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
  renderV1(<ErrorText>Bad value</ErrorText>);
  expect(screen.getByRole("alert").textContent).toBe("Bad value");
});

// FormField (P1-T06) passes `error` into Field, so this precedence is what a form control gets.
it.each(
  CONTROLS,
)("a %s's own invalid, disabled and readOnly win over its Field's", (_, make) => {
  renderV1(
    <Field label="Name" error="x" disabled readOnly>
      {make({ invalid: false, disabled: false, readOnly: false })}
    </Field>,
  );
  const control = screen.getByLabelText("Name") as HTMLInputElement;
  expect(control).not.toHaveAttribute("aria-invalid");
  expect(control).toBeEnabled();
  expect(control.readOnly).toBe(false);
  expect(frameOf(control)).not.toHaveAttribute("data-invalid");
});

it("invalid={false} on a Field keeps its error text but not the invalid mark", () => {
  renderV1(
    <Field label="Name" error="Taken" invalid={false}>
      <Input />
    </Field>,
  );
  const control = screen.getByLabelText("Name");
  expect(control).not.toHaveAttribute("aria-invalid");
  expect(screen.getByText("Taken")).toBeInTheDocument();
});

it("gives the label an id that useFieldControl hands to a group control", () => {
  function Group() {
    const { labelId } = useFieldControl({});
    return <div role="radiogroup" aria-labelledby={labelId} />;
  }
  renderV1(
    <Field id="plan" label="Plan">
      <Group />
    </Field>,
  );
  expect(screen.getByRole("radiogroup", { name: "Plan" })).toBeInTheDocument();
  expect(screen.getByText("Plan")).toHaveAttribute("id", "plan-label");
});

it("fieldFrameVariants: focus within rings on the control, focus self on the frame", () => {
  expect(fieldFrameVariants()).toContain(
    "ui:has-[[data-slot=control]:focus-visible]:focus-ring",
  );
  const self = fieldFrameVariants({ focus: "self" });
  expect(self).toContain("ui:focus-visible:focus-ring");
  expect(self).not.toContain("has-[[data-slot=control]");
  expect(self).toContain("ui:data-readonly:bg-muted");
});
