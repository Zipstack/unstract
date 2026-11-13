import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it } from "vitest";
import { Field } from "./Field";
import { Input } from "./Input";
import { Textarea } from "./Textarea";

it("renders adornments around the control in order", () => {
  renderV1(
    <Input
      aria-label="URL"
      leading={<svg data-testid="icon" />}
      prefix="https://"
      suffix=".com"
      trailing={<button type="button">Go</button>}
    />,
  );
  const frame = screen.getByLabelText("URL").parentElement as HTMLElement;
  const slots = [...frame.children].map(
    (el) => (el as HTMLElement).dataset.slot,
  );
  expect(slots).toEqual([
    "field-leading",
    "field-prefix",
    "control",
    "field-suffix",
    "field-trailing",
  ]);
  expect(screen.getByRole("button", { name: "Go" })).toBeTruthy();
});

it("is 32 tall and takes the single focus treatment from its frame", () => {
  renderV1(<Input aria-label="Name" />);
  const frame = screen.getByLabelText("Name").parentElement as HTMLElement;
  expect(frame.dataset.slot).toBe("field-frame");
  expect(frame.className).toContain("ui:h-8");
  expect(frame.className).toContain(
    "ui:has-[[data-slot=control]:focus-visible]:focus-ring",
  );
});

it.each([
  ["invalid", { invalid: true }, "data-invalid"],
  ["disabled", { disabled: true }, "data-disabled"],
  ["read-only", { readOnly: true }, "data-readonly"],
])("marks the frame %s", (_, props, attribute) => {
  renderV1(<Input aria-label="Name" {...props} />);
  const input = screen.getByLabelText("Name");
  expect(input.parentElement?.hasAttribute(attribute)).toBe(true);
});

it("sets aria-invalid only when invalid", () => {
  const { rerender } = renderV1(<Input aria-label="Name" />);
  expect(screen.getByLabelText("Name").hasAttribute("aria-invalid")).toBe(
    false,
  );
  rerender(<Input aria-label="Name" invalid />);
  expect(screen.getByLabelText("Name").getAttribute("aria-invalid")).toBe(
    "true",
  );
});

it("describes the control by its prefix and suffix text, after the Field's", () => {
  renderV1(
    <Field label="Endpoint" helperText="Your API host">
      <Input prefix="https://" suffix="/v1" />
    </Field>,
  );
  expect(screen.getByLabelText("Endpoint")).toHaveAccessibleDescription(
    "Your API host https:// /v1",
  );
});

it("describes a standalone control by its suffix, keeping its own description", () => {
  renderV1(
    <>
      <span id="hint">Up to 100</span>
      <Input aria-label="Pages" aria-describedby="hint" suffix="pages" />
    </>,
  );
  expect(screen.getByLabelText("Pages")).toHaveAccessibleDescription(
    "Up to 100 pages",
  );
});

it.each([
  ["Input", (p: object) => <Input {...p} />],
  ["Textarea", (p: object) => <Textarea {...p} />],
])("marks a %s frame invalid from a spread aria-invalid, so frame and ARIA agree", (_, make) => {
  const { rerender } = renderV1(
    <Field label="Name">{make({ "aria-invalid": true })}</Field>,
  );
  const control = () => screen.getByLabelText("Name");
  expect(control()).toHaveAttribute("aria-invalid", "true");
  expect(control().closest("[data-slot=field-frame]")).toHaveAttribute(
    "data-invalid",
  );
  rerender(
    <Field label="Name" error="Taken">
      {make({ "aria-invalid": false })}
    </Field>,
  );
  expect(control()).toHaveAttribute("aria-invalid", "true");
  expect(control().closest("[data-slot=field-frame]")).toHaveAttribute(
    "data-invalid",
  );
});
