import { screen } from "@testing-library/react";
import { fieldControlClass, fieldFrameVariants } from "@v1/components/ui/form";
import { renderV1 } from "@v1/test";
import { expect, it, vi } from "vitest";
import { Chip } from "./Chip";
import { Combobox } from "./Combobox";
import { MultiSelect } from "./MultiSelect";
import { OptionRow } from "./OptionRow";
import { SegmentedControl } from "./SegmentedControl";
import { Select } from "./Select";

/*
 * Class guards for layout and forced colors, which happy-dom cannot render:
 * the classes are pinned here and were checked in Chromium (README, Forced
 * colors).
 */

const classes = (element: Element) => element.className.split(" ");

// Forced-colors mode drops backgrounds and shadows; it paints a transparent
// outline or border in the system colour instead.
const ACTIVE_OUTLINE = [
  "ui:data-active:outline-solid",
  "ui:data-active:outline-1",
  "ui:data-active:-outline-offset-1",
  "ui:data-active:outline-transparent",
];
const HIGHLIGHTED_OUTLINE = ACTIVE_OUTLINE.map((name) =>
  name.replace("data-active", "data-highlighted"),
);

it("keeps option rows from shrinking and outlines the active row for forced colors", () => {
  renderV1(
    <OptionRow
      id="o"
      option={{ value: "a", label: "A" }}
      selected={false}
      active
    />,
  );
  const row = classes(screen.getByRole("option"));
  expect(row).toContain("ui:shrink-0");
  expect(row).toEqual(expect.arrayContaining(ACTIVE_OUTLINE));
});

it("keeps Select's rows and its No options row from shrinking in the capped viewport", async () => {
  const { user, rerender } = renderV1(
    <Select aria-label="S" options={[{ value: "a", label: "A" }]} />,
  );
  await user.click(screen.getByRole("combobox", { hidden: true }));
  const row = classes(screen.getByRole("option", { name: "A" }));
  expect(row).toContain("ui:shrink-0");
  expect(row).toEqual(expect.arrayContaining(HIGHLIGHTED_OUTLINE));
  rerender(<Select aria-label="S" options={[]} />);
  expect(classes(screen.getByRole("option", { name: "No options" }))).toContain(
    "ui:shrink-0",
  );
});

it("borders SegmentedControl's track and its selected segment for forced colors", () => {
  renderV1(
    <SegmentedControl
      aria-label="View"
      options={[
        { value: "a", label: "A" },
        { value: "b", label: "B" },
      ]}
    />,
  );
  const group = classes(screen.getByRole("radiogroup"));
  // A border, not an outline: Radix sets an inline `outline: none` on the group.
  // 1px border + 1px padding is the 2px inset the pills had before.
  expect(group).toEqual(
    expect.arrayContaining(["ui:border", "ui:border-transparent", "ui:p-px"]),
  );
  expect(group).not.toContain("ui:p-0.5");
  // The 1px border replaces 1px of the 12px padding, so the width is unchanged.
  const item = classes(screen.getByRole("radio", { name: "A" }));
  expect(item).toEqual(
    expect.arrayContaining([
      "ui:px-3",
      "ui:data-[state=on]:border",
      "ui:data-[state=on]:border-transparent",
      "ui:data-[state=on]:px-2.75",
    ]),
  );
});

it("outlines a Chip inside its edge for forced colors", () => {
  renderV1(<Chip label="Tag" />);
  const chip = classes(
    screen.getByText("Tag").closest("[data-slot=chip]") as Element,
  );
  expect(chip).toEqual(
    expect.arrayContaining([
      "ui:outline",
      "ui:outline-transparent",
      "ui:-outline-offset-1",
    ]),
  );
});

const tokens = (list: string) => list.split(" ").filter(Boolean);

it("builds Select's trigger from the field frame with the focus ring on itself", () => {
  renderV1(<Select aria-label="S" options={[]} />);
  const trigger = classes(screen.getByRole("combobox", { name: "S" }));
  expect(trigger).toEqual(
    expect.arrayContaining(tokens(fieldFrameVariants({ focus: "self" }))),
  );
  expect(trigger).toContain("ui:cursor-pointer");
});

it.each([
  ["Combobox", <Combobox key="c" aria-label="F" />, "combobox"],
  ["MultiSelect", <MultiSelect key="m" aria-label="F" />, "multi-select"],
])("builds the %s frame from the field frame, ringed when its input is focused", (_, element, slot) => {
  renderV1(element);
  const input = screen.getByRole("combobox", { name: "F" });
  const frame = classes(input.closest(`[data-slot=${slot}]`) as Element);
  const expected = tokens(fieldFrameVariants({ focus: "within" })).filter(
    // MultiSelect grows past 32 as chips wrap, with a 4px gap between them.
    (name) => slot === "combobox" || !["ui:h-8", "ui:gap-1.5"].includes(name),
  );
  expect(frame).toEqual(expect.arrayContaining(expected));
  // A frame is a div: `focus-visible:` and `disabled:` never match on it.
  expect(frame.some((name) => /:(focus-visible|disabled):/.test(name))).toBe(
    false,
  );
  // MultiSelect's input keeps 64px for typing beside the chips.
  expect(classes(input)).toEqual(
    expect.arrayContaining(
      tokens(fieldControlClass).filter((name) =>
        slot === "combobox" ? true : name !== "ui:min-w-0",
      ),
    ),
  );
});

it("drops the frame transition under reduced motion", () => {
  expect(tokens(fieldFrameVariants())).toContain(
    "ui:motion-reduce:transition-none",
  );
});

// A 16px button whose `after` box reaches 4px past each edge: a 24px target.
const HIT_AREA = ["ui:relative", "ui:after:absolute", "ui:after:-inset-1"];

it("gives the 16px Clear and chip remove buttons a 24px hit area", () => {
  renderV1(
    <>
      <Combobox
        aria-label="C"
        options={[{ value: "a", label: "A" }]}
        value="a"
      />
      <Chip label="Tag" onRemove={vi.fn()} />
    </>,
  );
  for (const name of ["Clear", "Remove Tag"]) {
    const button = classes(screen.getByRole("button", { name }));
    expect(button).toContain("ui:size-4");
    expect(button).toEqual(expect.arrayContaining(HIT_AREA));
  }
});
