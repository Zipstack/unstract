import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it } from "vitest";
import { Chip } from "./Chip";
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
