import { fireEvent, screen } from "@testing-library/react";
import { expectNoA11yViolations, renderV1 } from "@v1/test";
import type { JSX } from "react";
import { expect, it, vi } from "vitest";
import { Listbox, VIRTUALIZE_ABOVE } from "./Listbox";
import type { SelectOption } from "./options";
import { useListbox } from "./useListbox";

const FRUIT: readonly SelectOption[] = [
  { value: "apple", label: "Apple" },
  { value: "banana", label: "Banana", description: "Yellow" },
  { value: "cherry", label: "Cherry" },
];

const many = (count: number): readonly SelectOption[] =>
  Array.from({ length: count }, (_, i) => ({
    value: `v${i}`,
    label: `Option ${i}`,
  }));

/** Gives every element a 320-tall box (the list cap), as a laid-out page would. */
function stubLayout() {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
    new DOMRect(0, 0, 320, 320),
  );
  for (const [prop, size] of [
    ["offsetHeight", 320],
    ["offsetWidth", 320],
    ["clientHeight", 320],
    ["clientWidth", 320],
    ["scrollHeight", 40_000],
  ] as const) {
    vi.spyOn(HTMLElement.prototype, prop, "get").mockReturnValue(size);
  }
}

type HarnessProps = Readonly<{
  options?: readonly SelectOption[];
  selected?: readonly string[];
  onSelect?: (option: SelectOption) => void;
  loading?: boolean;
  emptyText?: string;
  multiselectable?: boolean;
}>;

/** An input wired to useListbox, with the list always shown. */
function Harness({
  options = FRUIT,
  selected = [],
  onSelect = () => undefined,
  loading,
  emptyText,
  multiselectable,
}: HarnessProps): JSX.Element {
  const listbox = useListbox({ options, selected, onSelect, id: "fruit" });
  return (
    <div>
      <input
        aria-label="Fruit"
        {...listbox.comboboxProps}
        value={listbox.query}
        onChange={(event) => listbox.setQuery(event.target.value)}
        onKeyDown={listbox.onKeyDown}
      />
      <Listbox
        listbox={listbox}
        loading={loading}
        emptyText={emptyText}
        multiselectable={multiselectable}
      />
    </div>
  );
}

it("renders each option with its optionId inside the controlled listbox", () => {
  renderV1(<Harness selected={["banana"]} />);
  const list = screen.getByRole("listbox");
  expect(list.id).toBe("fruit-listbox");
  expect(screen.getByRole("combobox").getAttribute("aria-controls")).toBe(
    list.id,
  );
  const rows = screen.getAllByRole("option");
  expect(rows.map((row) => row.id)).toEqual([
    "fruit-option-0",
    "fruit-option-1",
    "fruit-option-2",
  ]);
  expect(rows.map((row) => row.getAttribute("aria-selected"))).toEqual([
    "false",
    "true",
    "false",
  ]);
  expect(list.hasAttribute("aria-multiselectable")).toBe(false);
  expect(list.hasAttribute("aria-busy")).toBe(false);
});

it("sits in one scroll element that holds the listbox", () => {
  renderV1(<Harness />);
  const scroll = document.querySelector('[data-slot="listbox-scroll"]');
  expect(scroll?.className).toContain("ui:overflow-auto");
  expect(scroll?.className).toContain("ui:flex-1");
  expect(scroll?.className).toContain("ui:min-h-0");
  expect(scroll?.firstElementChild).toBe(screen.getByRole("listbox"));
});

it("marks the listbox multiselectable when asked", () => {
  renderV1(<Harness multiselectable />);
  expect(screen.getByRole("listbox").getAttribute("aria-multiselectable")).toBe(
    "true",
  );
});

it("selects a clicked option and activates a hovered one", async () => {
  const onSelect = vi.fn();
  const { user } = renderV1(<Harness onSelect={onSelect} />);
  const input = screen.getByRole("combobox");
  await user.click(input);
  await user.keyboard("{ArrowDown}");
  fireEvent.mouseMove(screen.getByRole("option", { name: "Cherry" }));
  expect(input.getAttribute("aria-activedescendant")).toBe("fruit-option-2");
  expect(
    screen.getByRole("option", { name: "Cherry" }).hasAttribute("data-active"),
  ).toBe(true);
  await user.click(screen.getByRole("option", { name: "Cherry" }));
  expect(onSelect).toHaveBeenCalledWith(FRUIT[2]);
});

it("shows a loading row outside the listbox and marks the listbox busy", () => {
  renderV1(<Harness options={[]} loading />);
  const list = screen.getByRole("listbox");
  expect(list.getAttribute("aria-busy")).toBe("true");
  const status = screen.getByRole("status");
  expect(status.tagName).toBe("OUTPUT");
  expect(status.textContent).toBe("Loading…");
  expect(status.querySelector('[data-slot="spinner"]')).not.toBeNull();
  expect(list.contains(status)).toBe(false);
  expect(screen.queryByText("No options")).toBeNull();
});

it("says No options for an empty list and No matches for an empty filter", async () => {
  const { unmount } = renderV1(<Harness options={[]} />);
  const status = screen.getByRole("status");
  expect(status.textContent).toBe("No options");
  expect(screen.getByRole("listbox").contains(status)).toBe(false);
  unmount();
  const second = renderV1(<Harness />);
  expect(screen.queryByRole("status")).toBeNull();
  await second.user.type(screen.getByRole("combobox"), "zzz");
  expect(screen.getByRole("status").textContent).toBe("No matches");
});

it("uses the caller's empty text", () => {
  renderV1(<Harness options={[]} emptyText="No models yet" />);
  expect(screen.getByRole("status").textContent).toBe("No models yet");
});

it("scrolls the active row into view", async () => {
  const scrollIntoView = vi.spyOn(Element.prototype, "scrollIntoView");
  const { user } = renderV1(<Harness />);
  await user.click(screen.getByRole("combobox"));
  scrollIntoView.mockClear();
  await user.keyboard("{ArrowDown}{End}");
  const target = scrollIntoView.mock.contexts.at(-1) as Element;
  expect(target.id).toBe("fruit-option-2");
  expect(scrollIntoView).toHaveBeenLastCalledWith({ block: "nearest" });
});

it("renders every row of a list at the threshold", () => {
  renderV1(<Harness options={many(VIRTUALIZE_ABOVE)} />);
  expect(screen.getAllByRole("option")).toHaveLength(VIRTUALIZE_ABOVE);
  expect(screen.getByRole("listbox").className).not.toContain("ui:relative");
});

it("renders only the rows in view of a 1,000-option list", () => {
  stubLayout();
  const options = many(1000);
  const started = performance.now();
  renderV1(<Harness options={options} />);
  const elapsed = performance.now() - started;
  const rows = screen.getAllByRole("option");
  expect(rows.length).toBeGreaterThan(0);
  expect(rows.length).toBeLessThan(60);
  expect(elapsed).toBeLessThan(1000);
  expect(rows[0].id).toBe("fruit-option-0");
  const list = screen.getByRole("listbox");
  expect(list.className).toContain("ui:relative");
  expect(list.className).toContain("ui:h-(--listbox-height)");
  expect(list.style.getPropertyValue("--listbox-height")).toBe("33998px");
  const wrapper = rows[1].parentElement as HTMLElement;
  expect(wrapper.className).toContain("ui:translate-y-(--row-y)");
  expect(wrapper.style.getPropertyValue("--row-y")).toBe("34px");
  expect(document.querySelector('[data-slot="listbox-scroll"]')).not.toBeNull();
});

it("sizes a virtual row with a description taller", () => {
  stubLayout();
  const options = many(200).map((option, i) =>
    i === 0 ? { ...option, description: "First" } : option,
  );
  renderV1(<Harness options={options} />);
  const rows = screen.getAllByRole("option");
  expect(
    (rows[1].parentElement as HTMLElement).style.getPropertyValue("--row-y"),
  ).toBe("50px");
});

it("brings the active row of a virtual list into the rendered window", async () => {
  stubLayout();
  const { user } = renderV1(<Harness options={many(1000)} />);
  expect(document.getElementById("fruit-option-999")).toBeNull();
  await user.click(screen.getByRole("combobox"));
  await user.keyboard("{ArrowDown}{End}");
  const scroll = document.querySelector(
    '[data-slot="listbox-scroll"]',
  ) as HTMLElement;
  expect(scroll.scrollTop).toBeGreaterThan(0);
  // happy-dom moves scrollTop without the scroll event a browser fires.
  fireEvent.scroll(scroll);
  const last = document.getElementById("fruit-option-999");
  expect(last).not.toBeNull();
  expect(last?.hasAttribute("data-active")).toBe(true);
});

it("has no axe violations with options, while loading, and when empty", async () => {
  const { unmount } = renderV1(<Harness selected={["apple"]} />);
  await expectNoA11yViolations(document.body);
  unmount();
  const loading = renderV1(<Harness options={[]} loading />);
  await expectNoA11yViolations(document.body);
  loading.unmount();
  renderV1(<Harness options={[]} />);
  await expectNoA11yViolations(document.body);
});
