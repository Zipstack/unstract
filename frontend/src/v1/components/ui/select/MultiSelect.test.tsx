import { act, screen, waitFor } from "@testing-library/react";
import { expectNoA11yViolations, renderV1 } from "@v1/test";
import { expect, it, vi } from "vitest";
import { MultiSelect, type MultiSelectProps } from "./MultiSelect";
import type { SelectOption } from "./options";
import type { LoadOptions } from "./useAsyncOptions";

const TAGS: readonly SelectOption[] = [
  { value: "invoice", label: "Invoice" },
  { value: "receipt", label: "Receipt", description: "Paid" },
  { value: "archived", label: "Archived", disabled: true },
  { value: "contract", label: "Contract", keywords: ["agreement"] },
];

function input(): HTMLInputElement {
  return screen.getByRole("combobox", { name: "Tags" }) as HTMLInputElement;
}

const chipNames = () =>
  [...document.querySelectorAll('[data-slot="chip"]')].map(
    (chip) => chip.textContent,
  );

const option = (name: string | RegExp) => screen.getByRole("option", { name });

function setup(props: Partial<MultiSelectProps> = {}) {
  const onValueChange = vi.fn();
  const view = renderV1(
    <>
      <MultiSelect
        options={TAGS}
        placeholder="Add tags"
        aria-label="Tags"
        onValueChange={onValueChange}
        {...props}
      />
      <button type="button">Elsewhere</button>
    </>,
  );
  return { ...view, onValueChange };
}

it("shows a chip per value, in order, named by label with a remove button", () => {
  setup({ defaultValue: ["receipt", "invoice", "gone"] });
  expect(chipNames()).toEqual(["Receipt", "Invoice", "gone"]);
  expect(screen.getByRole("button", { name: "Remove Receipt" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Remove gone" })).toBeTruthy();
  expect(input().nextElementSibling).toBe(
    screen.getByRole("button", { name: "Show options" }),
  );
});

it("shows the placeholder only when nothing is selected", () => {
  const { unmount } = setup();
  expect(input().placeholder).toBe("Add tags");
  unmount();
  setup({ defaultValue: ["invoice"] });
  expect(input().placeholder).toBe("");
});

it("adds a chosen option as a chip and keeps the list open", async () => {
  const { user, onValueChange } = setup({ defaultValue: ["invoice"] });
  await user.type(input(), "con");
  await user.click(option("Contract"));
  expect(onValueChange).toHaveBeenLastCalledWith(["invoice", "contract"]);
  expect(chipNames()).toEqual(["Invoice", "Contract"]);
  expect(screen.getByRole("listbox")).toBeTruthy();
  expect(input().value).toBe("");
  expect(screen.getAllByRole("option")).toHaveLength(TAGS.length);
  expect(document.activeElement).toBe(input());
});

it("toggles the active option on Enter", async () => {
  const { user, onValueChange } = setup();
  await user.click(input());
  await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");
  expect(onValueChange).toHaveBeenLastCalledWith(["receipt"]);
  expect(screen.getByRole("listbox")).toBeTruthy();
  // The toggled option stays active, so the arrows carry on from it.
  expect(input().getAttribute("aria-activedescendant")).toBe(
    option(/Receipt/).id,
  );
  await user.keyboard("{ArrowDown}");
  expect(input().getAttribute("aria-activedescendant")).toBe(
    option("Contract").id,
  );
  await user.keyboard("{Enter}");
  expect(onValueChange).toHaveBeenLastCalledWith(["receipt", "contract"]);
  expect(chipNames()).toEqual(["Receipt", "Contract"]);
});

it("keeps a filtered option active after Enter clears the query", async () => {
  const { user, onValueChange } = setup();
  await user.type(input(), "agree{Enter}");
  expect(onValueChange).toHaveBeenLastCalledWith(["contract"]);
  expect(input().value).toBe("");
  expect(screen.getAllByRole("option")).toHaveLength(TAGS.length);
  expect(input().getAttribute("aria-activedescendant")).toBe(
    option("Contract").id,
  );
});

it("removes an already-selected option when chosen again, keeping the list open", async () => {
  const { user, onValueChange } = setup({
    defaultValue: ["invoice", "receipt"],
  });
  await user.click(screen.getByRole("button", { name: "Show options" }));
  await user.click(option("Invoice"));
  expect(onValueChange).toHaveBeenLastCalledWith(["receipt"]);
  expect(chipNames()).toEqual(["Receipt"]);
  expect(screen.getByRole("listbox")).toBeTruthy();
  expect(option("Invoice").getAttribute("aria-selected")).toBe("false");
});

it("is a multiselectable listbox that marks every chosen option", async () => {
  const { user } = setup({ defaultValue: ["invoice", "contract"] });
  await user.click(screen.getByRole("button", { name: "Show options" }));
  expect(screen.getByRole("listbox").getAttribute("aria-multiselectable")).toBe(
    "true",
  );
  const selected = screen
    .getAllByRole("option")
    .filter((row) => row.getAttribute("aria-selected") === "true")
    .map((row) => row.textContent);
  expect(selected).toEqual(["Invoice", "Contract"]);
});

it("removes a chip with its button and returns focus to the input", async () => {
  const { user, onValueChange } = setup({
    defaultValue: ["invoice", "receipt"],
  });
  await user.click(screen.getByRole("button", { name: "Remove Invoice" }));
  expect(onValueChange).toHaveBeenLastCalledWith(["receipt"]);
  expect(chipNames()).toEqual(["Receipt"]);
  expect(document.activeElement).toBe(input());
});

it("removes the last chip on Backspace in an empty input", async () => {
  const { user, onValueChange } = setup({
    defaultValue: ["invoice", "receipt"],
  });
  await user.click(input());
  await user.keyboard("{Backspace}");
  expect(onValueChange).toHaveBeenLastCalledWith(["invoice"]);
  expect(chipNames()).toEqual(["Invoice"]);
  await user.keyboard("{Backspace}{Backspace}");
  expect(chipNames()).toEqual([]);
  expect(onValueChange).toHaveBeenCalledTimes(2);
});

it("edits the text on Backspace when the input has some, keeping the chips", async () => {
  const { user, onValueChange } = setup({ defaultValue: ["invoice"] });
  await user.type(input(), "re{Backspace}");
  expect(input().value).toBe("r");
  expect(chipNames()).toEqual(["Invoice"]);
  expect(onValueChange).not.toHaveBeenCalled();
});

it("closes and clears the query on Escape", async () => {
  const { user, onValueChange } = setup();
  await user.type(input(), "con");
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(input().value).toBe("");
  expect(onValueChange).not.toHaveBeenCalled();
});

it("closes and clears the query when focus leaves", async () => {
  const { user } = setup();
  await user.type(input(), "con");
  await user.click(screen.getByRole("button", { name: "Elsewhere" }));
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(input().value).toBe("");
});

it("closes on Tab", async () => {
  const { user } = setup();
  await user.type(input(), "con");
  await user.tab();
  expect(screen.queryByRole("listbox")).toBeNull();
});

it("stays open when the input or a chip's remove button is pressed", async () => {
  const { user } = setup({ defaultValue: ["invoice", "receipt"] });
  await user.type(input(), "con");
  await user.click(input());
  expect(screen.getByRole("listbox")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Remove Invoice" }));
  expect(screen.getByRole("listbox")).toBeTruthy();
});

it("toggles the list with the chevron, keeping focus on the input", async () => {
  const { user } = setup();
  const chevron = screen.getByRole("button", { name: "Show options" });
  expect(chevron.tabIndex).toBe(-1);
  await user.type(input(), "con");
  // The press never takes focus from the input, even for a moment.
  const blurs = vi.fn();
  input().addEventListener("blur", blurs);
  await user.click(chevron);
  expect(blurs).not.toHaveBeenCalled();
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(chevron.getAttribute("aria-expanded")).toBe("false");
  expect(input().value).toBe("");
  expect(document.activeElement).toBe(input());
  await user.click(chevron);
  expect(screen.getByRole("listbox")).toBeTruthy();
  expect(document.activeElement).toBe(input());
  await user.click(chevron);
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(document.activeElement).toBe(input());
});

it("keeps the chips out of the tab order: Tab lands on the input", async () => {
  const { user } = renderV1(
    <>
      <button type="button">Before</button>
      <MultiSelect
        options={TAGS}
        aria-label="Tags"
        defaultValue={["invoice", "receipt"]}
      />
    </>,
  );
  await user.click(screen.getByRole("button", { name: "Before" }));
  await user.tab();
  expect(document.activeElement).toBe(input());
  expect(screen.getByRole("button", { name: "Remove Invoice" }).tabIndex).toBe(
    -1,
  );
  await expectNoA11yViolations(document.body);
});

it("collapses duplicates in a controlled value", () => {
  setup({ value: ["invoice", "invoice", "receipt"] });
  expect(chipNames()).toEqual(["Invoice", "Receipt"]);
});

it("follows a controlled value", async () => {
  const { user, onValueChange, rerender } = setup({ value: ["invoice"] });
  await user.click(screen.getByRole("button", { name: "Show options" }));
  await user.click(option("Contract"));
  expect(onValueChange).toHaveBeenLastCalledWith(["invoice", "contract"]);
  expect(chipNames()).toEqual(["Invoice"]);
  rerender(
    <MultiSelect options={TAGS} aria-label="Tags" value={["receipt"]} />,
  );
  expect(chipNames()).toEqual(["Receipt"]);
});

it("submits one hidden input per value when named", async () => {
  const { user } = setup({ name: "tags", defaultValue: ["invoice"] });
  const values = () =>
    [
      ...document.querySelectorAll<HTMLInputElement>(
        'input[type="hidden"][name="tags"]',
      ),
    ].map((hidden) => hidden.value);
  expect(values()).toEqual(["invoice"]);
  await user.click(screen.getByRole("button", { name: "Show options" }));
  await user.click(option("Contract"));
  expect(values()).toEqual(["invoice", "contract"]);
});

it("disables the input and the chips, and submits nothing, when disabled", () => {
  setup({ name: "tags", defaultValue: ["invoice"], disabled: true });
  const frame = input().closest('[data-slot="multi-select"]') as HTMLElement;
  expect(input().disabled).toBe(true);
  expect(
    (
      screen.getByRole("button", {
        name: "Remove Invoice",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  expect(frame.hasAttribute("data-disabled")).toBe(true);
  expect(document.querySelector('input[type="hidden"]')).toBeNull();
});

it("passes id, invalid and aria-describedby to the input", () => {
  setup({ id: "tags-input", invalid: true, "aria-describedby": "tags-help" });
  const frame = input().closest('[data-slot="multi-select"]') as HTMLElement;
  expect(input().id).toBe("tags-input");
  expect(input().getAttribute("aria-invalid")).toBe("true");
  expect(input().getAttribute("aria-describedby")).toBe("tags-help");
  expect(frame.hasAttribute("data-invalid")).toBe(true);
  expect(frame.className).toContain("ui:h-auto");
  expect(frame.className).not.toContain("ui:h-8");
});

it("names preset chips from selectedOptions before any load", () => {
  const load = vi.fn<LoadOptions>(() => new Promise(() => undefined));
  renderV1(
    <MultiSelect
      aria-label="Tags"
      loadOptions={load}
      value={["x", "y"]}
      selectedOptions={[{ value: "x", label: "Saved X" }]}
    />,
  );
  expect(chipNames()).toEqual(["Saved X", "y"]);
  expect(load).not.toHaveBeenCalled();
});

it("keeps a loaded chip's label after the query changes", async () => {
  const calls: {
    query: string;
    resolve: (options: readonly SelectOption[]) => void;
  }[] = [];
  const load = vi.fn<LoadOptions>(
    (query) =>
      new Promise((resolve) => {
        calls.push({ query, resolve });
      }),
  );
  const { user } = renderV1(
    <MultiSelect aria-label="Tags" loadOptions={load} />,
  );
  await user.type(input(), "a");
  await waitFor(() => expect(calls).toHaveLength(1));
  await act(async () => calls[0].resolve([{ value: "a", label: "Alpha" }]));
  await user.keyboard("{Enter}");
  expect(chipNames()).toEqual(["Alpha"]);
  await waitFor(() => expect(calls).toHaveLength(2));
  expect(calls[1].query).toBe("");
  await act(async () => calls[1].resolve([{ value: "b", label: "Beta" }]));
  expect(chipNames()).toEqual(["Alpha"]);
});

it("has no axe violations closed and open", async () => {
  const { user } = setup({ defaultValue: ["invoice"] });
  await expectNoA11yViolations(document.body);
  await user.click(screen.getByRole("button", { name: "Show options" }));
  await expectNoA11yViolations(document.body);
});
