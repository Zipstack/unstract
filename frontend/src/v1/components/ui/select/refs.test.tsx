import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { createRef } from "react";
import { expect, it, vi } from "vitest";
import { Combobox } from "./Combobox";
import { MultiSelect } from "./MultiSelect";
import type { SelectOption } from "./options";
import { SegmentedControl } from "./SegmentedControl";
import { Select } from "./Select";

/*
 * Where a caller's `ref` and `id` land: on the focusable element. A Select's
 * trigger button; a Combobox's or MultiSelect's text input (not the frame);
 * a SegmentedControl's radiogroup (not an item).
 */

const OPTIONS: readonly SelectOption[] = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
];

it("puts a Select's ref and id on the trigger button", () => {
  const ref = createRef<HTMLButtonElement>();
  renderV1(<Select ref={ref} id="s" aria-label="S" options={OPTIONS} />);
  const trigger = screen.getByRole("combobox", { name: "S" });
  expect(trigger.tagName).toBe("BUTTON");
  expect(ref.current).toBe(trigger);
  expect(trigger).toHaveAttribute("id", "s");
});

it("puts a Combobox's ref and id on the input, and still opens the list", async () => {
  const ref = createRef<HTMLInputElement>();
  const { user } = renderV1(
    <Combobox ref={ref} id="c" aria-label="C" options={OPTIONS} />,
  );
  const input = screen.getByRole("combobox", { name: "C" });
  expect(input.tagName).toBe("INPUT");
  expect(ref.current).toBe(input);
  expect(input).toHaveAttribute("id", "c");
  // The component's own ref to the input still works: the chevron refocuses it.
  await user.click(screen.getByRole("button", { name: "Show options" }));
  expect(document.activeElement).toBe(input);
});

it("puts a MultiSelect's ref and id on the input, and still focuses it from the frame", async () => {
  const ref = vi.fn();
  const { user, unmount } = renderV1(
    <MultiSelect ref={ref} id="m" aria-label="M" options={OPTIONS} />,
  );
  const input = screen.getByRole("combobox", { name: "M" });
  expect(input.tagName).toBe("INPUT");
  expect(ref).toHaveBeenCalledWith(input);
  expect(input).toHaveAttribute("id", "m");
  await user.click(screen.getByRole("button", { name: "Show options" }));
  expect(document.activeElement).toBe(input);
  unmount();
  expect(ref).toHaveBeenLastCalledWith(null);
});

it("puts a SegmentedControl's ref and id on the radiogroup, not an item", () => {
  const ref = createRef<HTMLDivElement>();
  renderV1(
    <SegmentedControl ref={ref} id="g" aria-label="G" options={OPTIONS} />,
  );
  const group = screen.getByRole("radiogroup", { name: "G" });
  expect(ref.current).toBe(group);
  expect(group).toHaveAttribute("id", "g");
  for (const radio of screen.getAllByRole("radio")) {
    expect(radio).not.toHaveAttribute("id");
  }
});
