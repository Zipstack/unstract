import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { Star } from "lucide-react";
import { expect, it, vi } from "vitest";
import { SegmentedControl, type SegmentedOption } from "./SegmentedControl";

const VIEWS: readonly SegmentedOption[] = [
  { value: "list", label: "List", icon: <Star aria-hidden /> },
  { value: "grid", label: "Grid" },
  { value: "board", label: "Board", disabled: true },
  { value: "table", label: "Table" },
];

function setup(props: Partial<Parameters<typeof SegmentedControl>[0]> = {}) {
  const onValueChange = vi.fn();
  const view = renderV1(
    <SegmentedControl
      options={VIEWS}
      aria-label="View"
      onValueChange={onValueChange}
      {...props}
    />,
  );
  return { ...view, onValueChange };
}

// Radix 1.1 renders a single-type ToggleGroup as a radiogroup of radios.
function item(name: string): HTMLElement {
  return screen.getByRole("radio", { name });
}

function selected(): string[] {
  return screen
    .getAllByRole("radio")
    .filter((radio) => radio.getAttribute("aria-checked") === "true")
    .map((radio) => radio.textContent ?? "");
}

it("renders a radiogroup named by aria-label with the selected item checked", () => {
  setup({ defaultValue: "grid" });
  const group = screen.getByRole("radiogroup", { name: "View" });
  expect(group.getAttribute("data-slot")).toBe("segmented-control");
  expect(item("Grid").getAttribute("aria-checked")).toBe("true");
  expect(item("Grid").getAttribute("data-state")).toBe("on");
  expect(item("List").getAttribute("aria-checked")).toBe("false");
  expect(item("List").getAttribute("data-state")).toBe("off");
  expect(selected()).toEqual(["Grid"]);
});

it("names each item by its label and renders the icon before it", () => {
  setup();
  const icon = item("List").querySelector('[data-slot="segmented-icon"]');
  expect(icon?.getAttribute("aria-hidden")).toBe("true");
  expect(icon?.querySelector("svg")).toBeTruthy();
  expect(item("List").firstElementChild).toBe(icon);
});

it("selects the first enabled option by default", () => {
  setup({
    options: [
      { value: "a", label: "Alpha", disabled: true },
      { value: "b", label: "Beta" },
      { value: "c", label: "Gamma" },
    ],
  });
  expect(selected()).toEqual(["Beta"]);
});

it("selects on click", async () => {
  const { user, onValueChange } = setup();
  await user.click(item("Table"));
  expect(onValueChange).toHaveBeenCalledExactlyOnceWith("table");
  expect(selected()).toEqual(["Table"]);
});

it("keeps the selected item selected when it is clicked again", async () => {
  const { user, onValueChange } = setup({ defaultValue: "grid" });
  await user.click(item("Grid"));
  expect(onValueChange).not.toHaveBeenCalled();
  expect(selected()).toEqual(["Grid"]);
});

it("follows a controlled value and reports changes without applying them", async () => {
  const { user, onValueChange, rerender } = setup({ value: "grid" });
  await user.click(item("Table"));
  expect(onValueChange).toHaveBeenCalledExactlyOnceWith("table");
  expect(selected()).toEqual(["Grid"]);
  rerender(
    <SegmentedControl
      options={VIEWS}
      aria-label="View"
      value="table"
      onValueChange={onValueChange}
    />,
  );
  expect(selected()).toEqual(["Table"]);
});

it("moves focus with the arrows, skipping the disabled item, and selects on Enter and Space", async () => {
  const { user, onValueChange } = setup({ defaultValue: "list" });
  await user.tab();
  expect(document.activeElement).toBe(item("List"));
  await user.keyboard("{ArrowRight}");
  expect(document.activeElement).toBe(item("Grid"));
  await user.keyboard("{ArrowRight}");
  expect(document.activeElement).toBe(item("Table"));
  await user.keyboard("{Enter}");
  expect(onValueChange).toHaveBeenLastCalledWith("table");
  expect(selected()).toEqual(["Table"]);
  await user.keyboard("{ArrowLeft}");
  expect(document.activeElement).toBe(item("Grid"));
  await user.keyboard(" ");
  expect(onValueChange).toHaveBeenLastCalledWith("grid");
  expect(selected()).toEqual(["Grid"]);
});

it("ignores ArrowUp and ArrowDown", async () => {
  const { user } = setup({ defaultValue: "list" });
  await user.tab();
  await user.keyboard("{ArrowDown}");
  expect(document.activeElement).toBe(item("List"));
  await user.keyboard("{ArrowUp}");
  expect(document.activeElement).toBe(item("List"));
});

it("jumps to the first and last items with Home and End", async () => {
  const { user } = setup({ defaultValue: "grid" });
  await user.tab();
  expect(document.activeElement).toBe(item("Grid"));
  await user.keyboard("{End}");
  expect(document.activeElement).toBe(item("Table"));
  await user.keyboard("{Home}");
  expect(document.activeElement).toBe(item("List"));
});

it("does not select a disabled item", async () => {
  const { user, onValueChange } = setup({ defaultValue: "list" });
  expect(item("Board")).toHaveProperty("disabled", true);
  await user.click(item("Board"));
  expect(onValueChange).not.toHaveBeenCalled();
  expect(selected()).toEqual(["List"]);
});

it("disables every item when the control is disabled", async () => {
  const { user, onValueChange } = setup({ disabled: true });
  for (const radio of screen.getAllByRole("radio")) {
    expect(radio).toHaveProperty("disabled", true);
  }
  await user.click(item("Table"));
  expect(onValueChange).not.toHaveBeenCalled();
});

it("puts className on the group", () => {
  setup({ className: "ui:w-full" });
  expect(screen.getByRole("radiogroup").className).toContain("ui:w-full");
});

it("throws for fewer than 2 options", () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  expect(() =>
    renderV1(
      <SegmentedControl
        options={[{ value: "a", label: "Alpha" }]}
        aria-label="View"
      />,
    ),
  ).toThrow("SegmentedControl needs 2 to 5 options");
});

it("throws for more than 5 options", () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  const six = ["a", "b", "c", "d", "e", "f"].map((value) => ({
    value,
    label: value.toUpperCase(),
  }));
  expect(() =>
    renderV1(<SegmentedControl options={six} aria-label="View" />),
  ).toThrow("SegmentedControl needs 2 to 5 options");
});
