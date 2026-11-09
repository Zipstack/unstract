import { act } from "@testing-library/react";
import { renderHookV1 } from "@v1/test";
import type { KeyboardEvent } from "react";
import { expect, it, vi } from "vitest";
import type { SelectOption } from "./options";
import { type UseListboxOptions, useListbox } from "./useListbox";

const OPTIONS: readonly SelectOption[] = [
  { value: "alpha", label: "Alpha" },
  { value: "beta", label: "Beta", disabled: true },
  { value: "gamma", label: "Gamma", keywords: ["third"] },
  { value: "delta", label: "Delta" },
  { value: "epsilon", label: "Epsilon", disabled: true },
];

type Props = Partial<UseListboxOptions>;

function setup(props: Props = {}) {
  const onSelect = vi.fn();
  const hook = renderHookV1(
    (p: Props) =>
      useListbox({
        options: OPTIONS,
        selected: [],
        onSelect,
        id: "fruit",
        ...p,
      }),
    { initialProps: props },
  );
  const press = (key: string) => {
    const preventDefault = vi.fn();
    act(() =>
      hook.result.current.onKeyDown({
        key,
        preventDefault,
        nativeEvent: { isComposing: false },
      } as unknown as KeyboardEvent<HTMLElement>),
    );
    return preventDefault;
  };
  return { ...hook, onSelect, press };
}

it("starts closed with the combobox props pointing at the list", () => {
  const { result } = setup();
  expect(result.current.open).toBe(false);
  expect(result.current.listId).toBe("fruit-listbox");
  expect(result.current.optionId(3)).toBe("fruit-option-3");
  expect(result.current.activeId).toBeUndefined();
  expect(result.current.comboboxProps).toEqual({
    role: "combobox",
    "aria-expanded": false,
    "aria-controls": "fruit-listbox",
    "aria-autocomplete": "list",
    "aria-activedescendant": undefined,
  });
});

it("opens on ArrowDown at the first enabled option when nothing is selected", () => {
  const { result, press } = setup({
    options: [{ ...OPTIONS[1] }, ...OPTIONS.slice(2)],
  });
  const prevented = press("ArrowDown");
  expect(prevented).toHaveBeenCalled();
  expect(result.current.open).toBe(true);
  expect(result.current.activeIndex).toBe(1);
  expect(result.current.activeId).toBe("fruit-option-1");
  expect(result.current.comboboxProps["aria-expanded"]).toBe(true);
  expect(result.current.comboboxProps["aria-activedescendant"]).toBe(
    "fruit-option-1",
  );
});

it("opens on ArrowDown or ArrowUp at the first selected option", () => {
  const down = setup({ selected: ["delta", "gamma"] });
  down.press("ArrowDown");
  expect(down.result.current.activeIndex).toBe(2);
  const up = setup({ selected: ["delta"] });
  up.press("ArrowUp");
  expect(up.result.current.open).toBe(true);
  expect(up.result.current.activeIndex).toBe(3);
});

it("moves with the arrows, skipping disabled options and clamping at the ends", () => {
  const { result, press } = setup();
  press("ArrowDown");
  expect(result.current.activeIndex).toBe(0);
  press("ArrowDown");
  expect(result.current.activeIndex).toBe(2);
  press("ArrowDown");
  expect(result.current.activeIndex).toBe(3);
  expect(press("ArrowDown")).toHaveBeenCalled();
  expect(result.current.activeIndex).toBe(3);
  press("ArrowUp");
  expect(result.current.activeIndex).toBe(2);
  press("ArrowUp");
  expect(result.current.activeIndex).toBe(0);
  press("ArrowUp");
  expect(result.current.activeIndex).toBe(0);
});

it("jumps to the first and last enabled option with Home and End while open", () => {
  const { result, press } = setup();
  press("ArrowDown");
  expect(press("End")).toHaveBeenCalled();
  expect(result.current.activeIndex).toBe(3);
  expect(press("Home")).toHaveBeenCalled();
  expect(result.current.activeIndex).toBe(0);
});

it("leaves Home and End to the caret while closed", () => {
  const { result, press } = setup();
  act(() => result.current.setActiveIndex(2));
  expect(press("End")).not.toHaveBeenCalled();
  expect(press("Home")).not.toHaveBeenCalled();
  expect(result.current.open).toBe(false);
  expect(result.current.activeIndex).toBe(2);
});

it("selects the active option with Enter while open", () => {
  const { result, press, onSelect } = setup();
  expect(press("Enter")).not.toHaveBeenCalled();
  expect(onSelect).not.toHaveBeenCalled();
  press("ArrowDown");
  press("ArrowDown");
  expect(press("Enter")).toHaveBeenCalled();
  expect(onSelect).toHaveBeenCalledWith(OPTIONS[2]);
  expect(result.current.open).toBe(true);
});

it("does not select a disabled active option", () => {
  const { result, press, onSelect } = setup();
  press("ArrowDown");
  act(() => result.current.setActiveIndex(1));
  expect(press("Enter")).not.toHaveBeenCalled();
  expect(onSelect).not.toHaveBeenCalled();
});

it("closes with Escape, preventing the default only while open", () => {
  const { result, press } = setup();
  expect(press("Escape")).not.toHaveBeenCalled();
  press("ArrowDown");
  expect(press("Escape")).toHaveBeenCalled();
  expect(result.current.open).toBe(false);
  expect(result.current.activeId).toBeUndefined();
});

it("closes with Tab without preventing the focus move", () => {
  const { result, press } = setup();
  press("ArrowDown");
  expect(press("Tab")).not.toHaveBeenCalled();
  expect(result.current.open).toBe(false);
});

it("ignores other keys", () => {
  const { result, press } = setup();
  expect(press("a")).not.toHaveBeenCalled();
  expect(result.current.open).toBe(false);
});

it("filters by label and keyword, opening at the first enabled match", () => {
  const { result } = setup();
  act(() => result.current.setQuery("ta"));
  expect(result.current.open).toBe(true);
  expect(result.current.query).toBe("ta");
  // "Beta" (disabled) and "Delta" match; the active option skips Beta.
  expect(result.current.visible.map((o) => o.value)).toEqual(["beta", "delta"]);
  expect(result.current.activeIndex).toBe(1);
  act(() => result.current.setQuery("third"));
  expect(result.current.visible.map((o) => o.value)).toEqual(["gamma"]);
  expect(result.current.activeIndex).toBe(0);
});

it("does not open for an empty query", () => {
  const { result } = setup();
  act(() => result.current.setQuery(""));
  expect(result.current.open).toBe(false);
});

it("keeps every option when filtering is off", () => {
  const { result } = setup({ filter: false });
  act(() => result.current.setQuery("zzz"));
  expect(result.current.visible).toBe(OPTIONS);
  expect(result.current.activeIndex).toBe(0);
});

it("moves to the first enabled option when the active option vanishes", () => {
  const { result, press, rerender } = setup();
  press("ArrowDown");
  press("End");
  expect(result.current.activeIndex).toBe(3);
  rerender({ options: OPTIONS.slice(0, 2) });
  expect(result.current.activeIndex).toBe(0);
  expect(result.current.activeId).toBe("fruit-option-0");
});

it("follows the active option to its new index when the list changes", () => {
  const { result, press, rerender } = setup();
  press("ArrowDown");
  press("ArrowDown");
  expect(result.current.visible[result.current.activeIndex].value).toBe(
    "gamma",
  );
  rerender({ options: [OPTIONS[2], OPTIONS[3]] });
  expect(result.current.activeIndex).toBe(0);
});

it("has nothing active when no option is enabled", () => {
  const { result, press, onSelect } = setup({
    options: [OPTIONS[1], OPTIONS[4]],
  });
  press("ArrowDown");
  expect(result.current.open).toBe(true);
  expect(result.current.activeIndex).toBe(-1);
  expect(result.current.activeId).toBeUndefined();
  press("Enter");
  expect(onSelect).not.toHaveBeenCalled();
});

it("opens through setOpen at the first selected option", () => {
  const { result } = setup({ selected: ["delta"] });
  act(() => result.current.setOpen(true));
  expect(result.current.open).toBe(true);
  expect(result.current.activeIndex).toBe(3);
  expect(result.current.activeId).toBe("fruit-option-3");
  act(() => result.current.setOpen(false));
  expect(result.current.open).toBe(false);
  expect(result.current.activeId).toBeUndefined();
});

it("opens through setOpen at the first enabled option with no selection", () => {
  const { result, press } = setup();
  press("ArrowDown");
  press("End");
  act(() => result.current.setOpen(false));
  act(() => result.current.setOpen(true));
  expect(result.current.activeIndex).toBe(0);
});

it("does not open on a disabled selected option", () => {
  const down = setup({ selected: ["beta"] });
  down.press("ArrowDown");
  expect(down.result.current.activeIndex).toBe(0);
  const click = setup({ selected: ["beta"] });
  act(() => click.result.current.setOpen(true));
  expect(click.result.current.activeIndex).toBe(0);
});
