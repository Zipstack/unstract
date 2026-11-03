import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { Input } from "./Input";

it("renders adornments around the control in order", () => {
  render(
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
  render(<Input aria-label="Name" />);
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
  render(<Input aria-label="Name" {...props} />);
  const input = screen.getByLabelText("Name");
  expect(input.parentElement?.hasAttribute(attribute)).toBe(true);
});

it("sets aria-invalid only when invalid", () => {
  const { rerender } = render(<Input aria-label="Name" />);
  expect(screen.getByLabelText("Name").hasAttribute("aria-invalid")).toBe(
    false,
  );
  rerender(<Input aria-label="Name" invalid />);
  expect(screen.getByLabelText("Name").getAttribute("aria-invalid")).toBe(
    "true",
  );
});
