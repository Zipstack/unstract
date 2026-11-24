import { screen } from "@testing-library/react";
import { Field } from "@v1/components/ui/form";
import { renderV1 } from "@v1/test";
import type { JSX } from "react";
import { expect, it } from "vitest";
import { Combobox } from "./Combobox";
import { MultiSelect } from "./MultiSelect";
import type { SelectOption } from "./options";
import { SegmentedControl } from "./SegmentedControl";
import { Select } from "./Select";

const OPTIONS: readonly SelectOption[] = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
];

type Props = Readonly<{
  invalid?: boolean;
  disabled?: boolean;
  id?: string;
  "aria-describedby"?: string;
  "aria-label"?: string;
}>;

/** Each field, with the element that carries its name and state. */
const FIELDS: [string, (props: Props) => JSX.Element, () => HTMLElement][] = [
  [
    "Select",
    (p) => <Select options={OPTIONS} {...p} />,
    () => screen.getByRole("combobox"),
  ],
  [
    "Combobox",
    (p) => <Combobox options={OPTIONS} {...p} />,
    () => screen.getByRole("combobox"),
  ],
  [
    "MultiSelect",
    (p) => <MultiSelect options={OPTIONS} {...p} />,
    () => screen.getByRole("combobox"),
  ],
  [
    "SegmentedControl",
    (p) => <SegmentedControl options={OPTIONS} {...p} />,
    () => screen.getByRole("radiogroup"),
  ],
];

const frameOf = (control: HTMLElement) =>
  control.closest("[data-invalid], [data-disabled]") ?? control;

/** The control is disabled; for a radiogroup, every radio in it is. */
const isDisabled = (control: HTMLElement) =>
  control.getAttribute("role") === "radiogroup"
    ? [...control.querySelectorAll("[role=radio]")].every((radio) =>
        radio.hasAttribute("disabled"),
      )
    : control.hasAttribute("disabled");

it.each(FIELDS)("is named by the Field's label: %s", (_, make, get) => {
  renderV1(<Field label="Mode">{make({})}</Field>);
  expect(get()).toHaveAccessibleName("Mode");
});

it.each(
  FIELDS,
)("wires a %s to the Field's id, helper, error and disabled", (_, make, get) => {
  renderV1(
    <Field label="Mode" id="mode" helperText="Help" error="Bad" disabled>
      {make({})}
    </Field>,
  );
  const control = get();
  expect(control).toHaveAccessibleName("Mode");
  expect(control.id).toBe("mode");
  expect(control.getAttribute("aria-describedby")).toBe(
    "mode-helper mode-error",
  );
  expect(control.getAttribute("aria-invalid")).toBe("true");
  expect(frameOf(control).hasAttribute("data-invalid")).toBe(true);
  expect(isDisabled(control)).toBe(true);
});

it.each(
  FIELDS,
)("lets a %s's own props win over the Field's", (_, make, get) => {
  renderV1(
    <Field label="Mode" error="Bad" disabled>
      {make({
        invalid: false,
        disabled: false,
        "aria-describedby": "own",
        "aria-label": "Own name",
      })}
    </Field>,
  );
  const control = get();
  expect(control).toHaveAccessibleName("Own name");
  expect(control.hasAttribute("aria-invalid")).toBe(false);
  expect(isDisabled(control)).toBe(false);
  expect(control.getAttribute("aria-describedby")?.split(" ")).toContain("own");
});

it.each(FIELDS)("leaves a standalone %s as it was", (_, make, get) => {
  renderV1(make({ "aria-label": "C", id: "own" }));
  const control = get();
  expect(control).toHaveAccessibleName("C");
  expect(control.id).toBe("own");
  expect(control.hasAttribute("aria-describedby")).toBe(false);
  expect(control.hasAttribute("aria-invalid")).toBe(false);
  expect(control.hasAttribute("aria-labelledby")).toBe(false);
});

it("names the open Combobox and MultiSelect list by the Field's label", async () => {
  const { user } = renderV1(
    <>
      <Field label="One">
        <Combobox options={OPTIONS} />
      </Field>
      <Field label="Many">
        <MultiSelect options={OPTIONS} />
      </Field>
    </>,
  );
  await user.click(screen.getByRole("combobox", { name: "One" }));
  expect(screen.getByRole("listbox", { name: "One" })).toBeTruthy();
  await user.click(screen.getByRole("combobox", { name: "Many" }));
  expect(screen.getByRole("listbox", { name: "Many" })).toBeTruthy();
});
