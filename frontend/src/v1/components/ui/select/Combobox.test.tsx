import { act, screen, waitFor } from "@testing-library/react";
import { expectNoA11yViolations, renderV1, stubLayout } from "@v1/test";
import { Star } from "lucide-react";
import { expect, it, vi } from "vitest";
import { Combobox, type ComboboxProps } from "./Combobox";
import type { SelectOption } from "./options";
import type { LoadOptions } from "./useAsyncOptions";

const MODELS: readonly SelectOption[] = [
  { value: "claude", label: "Claude", leading: <Star aria-hidden /> },
  { value: "gemini", label: "Gemini", description: "Google" },
  { value: "grok", label: "Grok", disabled: true },
  { value: "gemma", label: "Gemma", keywords: ["gemma-3"] },
  { value: "llama", label: "Llama" },
];

function input(): HTMLInputElement {
  return screen.getByRole("combobox", { name: "Model" }) as HTMLInputElement;
}

const optionNames = () =>
  screen.queryAllByRole("option").map((option) => option.textContent);

function setup(props: Partial<ComboboxProps> = {}) {
  const onValueChange = vi.fn();
  const view = renderV1(
    <>
      <Combobox
        options={MODELS}
        placeholder="Pick a model"
        aria-label="Model"
        onValueChange={onValueChange}
        {...props}
      />
      <button type="button">Elsewhere</button>
    </>,
  );
  return { ...view, onValueChange };
}

/** A loader whose every call waits until the test settles it. */
function deferredLoader() {
  const calls: {
    query: string;
    resolve: (options: readonly SelectOption[]) => void;
    reject: (error: unknown) => void;
  }[] = [];
  const load = vi.fn<LoadOptions>(
    (query) =>
      new Promise((resolve, reject) => {
        calls.push({ query, resolve, reject });
      }),
  );
  return { load, calls };
}

const opt = (label: string): SelectOption => ({
  value: label.toLowerCase(),
  label,
});

it("is a combobox named by aria-label that focus alone does not open", async () => {
  const { user } = setup();
  expect(input().getAttribute("aria-autocomplete")).toBe("list");
  expect(input().placeholder).toBe("Pick a model");
  await user.click(input());
  expect(document.activeElement).toBe(input());
  expect(input().getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByRole("listbox")).toBeNull();
});

it("opens and filters on typing, matching labels and keywords", async () => {
  const { user } = setup();
  await user.type(input(), "gem");
  expect(input().getAttribute("aria-expanded")).toBe("true");
  expect(input().getAttribute("aria-controls")).toBe(
    screen.getByRole("listbox").id,
  );
  expect(optionNames()).toEqual(["GeminiGoogle", "Gemma"]);
  await user.clear(input());
  await user.type(input(), "-3");
  expect(optionNames()).toEqual(["Gemma"]);
});

it("opens on ArrowDown and selects the active option on Enter", async () => {
  const { user, onValueChange } = setup();
  await user.click(input());
  await user.keyboard("{ArrowDown}");
  expect(screen.getByRole("listbox")).toBeTruthy();
  await user.keyboard("{ArrowDown}");
  const gemini = screen.getByRole("option", { name: /Gemini/ });
  expect(input().getAttribute("aria-activedescendant")).toBe(gemini.id);
  await user.keyboard("{Enter}");
  expect(onValueChange).toHaveBeenCalledWith("gemini", MODELS[1]);
  expect(input().value).toBe("Gemini");
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(input().getAttribute("aria-expanded")).toBe("false");
});

it("selects a clicked option and keeps focus on the input", async () => {
  const { user, onValueChange } = setup();
  await user.type(input(), "ll");
  await user.click(screen.getByRole("option", { name: "Llama" }));
  expect(onValueChange).toHaveBeenCalledWith("llama", MODELS[4]);
  expect(input().value).toBe("Llama");
  expect(document.activeElement).toBe(input());
});

it("shows the selected option's leading before the input", () => {
  setup({ defaultValue: "claude" });
  const frame = input().closest('[data-slot="combobox"]') as HTMLElement;
  expect(input().value).toBe("Claude");
  const leading = frame.querySelector('[data-slot="option-leading"]');
  expect(leading?.nextElementSibling).toBe(input());
});

it("restores the selected label on Escape without changing the value", async () => {
  const { user, onValueChange } = setup({ defaultValue: "llama" });
  await user.type(input(), "{Backspace}{Backspace}x");
  expect(input().value).toBe("Llax");
  expect(screen.getByRole("listbox")).toBeTruthy();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(input().value).toBe("Llama");
  expect(onValueChange).not.toHaveBeenCalled();
});

it("empties the input on Escape when nothing is selected", async () => {
  const { user } = setup();
  await user.type(input(), "gem");
  await user.keyboard("{Escape}");
  expect(input().value).toBe("");
  // The query is gone: reopening lists everything.
  await user.keyboard("{ArrowDown}");
  expect(optionNames()).toHaveLength(MODELS.length);
});

it("closes and restores the label when focus leaves", async () => {
  const { user } = setup({ defaultValue: "gemma" });
  await user.clear(input());
  await user.type(input(), "cl");
  expect(screen.getByRole("listbox")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Elsewhere" }));
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(input().value).toBe("Gemma");
});

it("stays open when the list's padding is pressed", async () => {
  const { user } = setup();
  await user.type(input(), "gem");
  await user.click(
    document.querySelector('[data-slot="listbox-scroll"]') as HTMLElement,
  );
  expect(screen.getByRole("listbox")).toBeTruthy();
  expect(document.activeElement).toBe(input());
  expect(input().value).toBe("gem");
});

it("stays open when the input is pressed again", async () => {
  const { user } = setup();
  await user.type(input(), "gem");
  await user.click(input());
  expect(screen.getByRole("listbox")).toBeTruthy();
  expect(input().value).toBe("gem");
});

it("restores the label when Tab moves to the clear button", async () => {
  const { user } = setup({ defaultValue: "gemma" });
  await user.clear(input());
  await user.type(input(), "cl");
  await user.tab();
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "Clear" }),
  );
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(input().value).toBe("Gemma");
});

it("jumps to the first and last enabled option on Home and End", async () => {
  const { user } = setup();
  await user.click(input());
  await user.keyboard("{ArrowDown}{End}");
  expect(input().getAttribute("aria-activedescendant")).toBe(
    screen.getByRole("option", { name: "Llama" }).id,
  );
  await user.keyboard("{Home}");
  expect(input().getAttribute("aria-activedescendant")).toBe(
    screen.getByRole("option", { name: "Claude" }).id,
  );
});

it("never activates a disabled option, and Enter on one does nothing", async () => {
  const { user, onValueChange } = setup();
  await user.click(input());
  await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}");
  expect(input().getAttribute("aria-activedescendant")).toBe(
    screen.getByRole("option", { name: "Gemma" }).id,
  );
  await user.clear(input());
  await user.type(input(), "grok");
  expect(optionNames()).toEqual(["Grok"]);
  expect(input().hasAttribute("aria-activedescendant")).toBe(false);
  await user.keyboard("{Enter}");
  await user.click(screen.getByRole("option", { name: "Grok" }));
  expect(onValueChange).not.toHaveBeenCalled();
  expect(screen.getByRole("listbox")).toBeTruthy();
});

it("clears the value with the clear button", async () => {
  const { user, onValueChange } = setup({ defaultValue: "gemini" });
  await user.click(screen.getByRole("button", { name: "Clear" }));
  expect(onValueChange).toHaveBeenCalledWith(null, null);
  expect(input().value).toBe("");
  expect(screen.queryByRole("button", { name: "Clear" })).toBeNull();
  expect(document.activeElement).toBe(input());
});

it("hides the clear button with no value or when disabled", () => {
  const { unmount } = setup();
  expect(screen.queryByRole("button", { name: "Clear" })).toBeNull();
  unmount();
  setup({ defaultValue: "gemini", disabled: true });
  expect(screen.queryByRole("button", { name: "Clear" })).toBeNull();
});

it("toggles the list with the chevron, keeping focus on the input", async () => {
  const { user } = setup({ defaultValue: "gemma" });
  const chevron = screen.getByRole("button", { name: "Show options" });
  expect(chevron.tabIndex).toBe(-1);
  await user.click(chevron);
  expect(document.activeElement).toBe(input());
  expect(chevron.getAttribute("aria-expanded")).toBe("true");
  expect(input().getAttribute("aria-activedescendant")).toBe(
    screen.getByRole("option", { name: "Gemma" }).id,
  );
  await user.click(chevron);
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(chevron.getAttribute("aria-expanded")).toBe("false");
  expect(document.activeElement).toBe(input());
});

it("follows a controlled value", async () => {
  const { user, onValueChange, rerender } = setup({ value: "claude" });
  await user.click(input());
  await user.keyboard("{ArrowDown}{End}{Enter}");
  expect(onValueChange).toHaveBeenCalledWith("llama", MODELS[4]);
  expect(input().value).toBe("Claude");
  rerender(<Combobox options={MODELS} aria-label="Model" value="gemma" />);
  expect(input().value).toBe("Gemma");
});

it("submits the value through a hidden input when named", async () => {
  const { user } = setup({ name: "model", defaultValue: "gemini" });
  const hidden = document.querySelector<HTMLInputElement>(
    'input[type="hidden"][name="model"]',
  );
  expect(hidden?.value).toBe("gemini");
  await user.click(screen.getByRole("button", { name: "Clear" }));
  expect(hidden?.value).toBe("");
});

it("omits the hidden input when disabled", () => {
  setup({ name: "model", defaultValue: "gemini", disabled: true });
  expect(document.querySelector('input[type="hidden"]')).toBeNull();
});

it("passes id, invalid, disabled and aria-describedby to the input", () => {
  setup({
    id: "model-input",
    invalid: true,
    disabled: true,
    "aria-describedby": "model-help",
  });
  const frame = input().closest('[data-slot="combobox"]') as HTMLElement;
  expect(input().id).toBe("model-input");
  expect(input().getAttribute("aria-invalid")).toBe("true");
  expect(input().getAttribute("aria-describedby")).toBe("model-help");
  expect(input().disabled).toBe(true);
  expect(frame.hasAttribute("data-invalid")).toBe(true);
  expect(frame.className).toContain(
    "ui:has-[[data-slot=control]:focus-visible]:focus-ring",
  );
  expect(frame.className).not.toContain("ui:focus-within:focus-ring");
  expect(frame.hasAttribute("data-disabled")).toBe(true);
  expect(
    (screen.getByRole("button", { name: "Show options" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
});

it("loads options when the list first opens and shows a loading row", async () => {
  const { load, calls } = deferredLoader();
  const { user } = setup({ options: undefined, loadOptions: load });
  expect(load).not.toHaveBeenCalled();
  await user.click(input());
  await user.keyboard("{ArrowDown}");
  await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
  expect(calls[0].query).toBe("");
  expect(screen.getByRole("status").textContent).toBe("Loading…");
  expect(screen.getByRole("listbox").getAttribute("aria-busy")).toBe("true");
  await act(async () => calls[0].resolve([opt("Alpha"), opt("Beta")]));
  expect(optionNames()).toEqual(["Alpha", "Beta"]);
  expect(screen.queryByRole("status")).toBeNull();
  await user.keyboard("{ArrowDown}{Enter}");
  expect(input().value).toBe("Beta");
});

it("shows the latest query's options when responses arrive out of order", async () => {
  const { load, calls } = deferredLoader();
  const { user } = setup({ options: undefined, loadOptions: load });
  await user.type(input(), "a");
  await waitFor(() => expect(calls).toHaveLength(1));
  await user.type(input(), "b");
  await waitFor(() => expect(calls).toHaveLength(2));
  expect(calls.map((call) => call.query)).toEqual(["a", "ab"]);
  // The server's answer for "ab" need not contain "ab": it is not refiltered.
  await act(async () => calls[1].resolve([opt("Server One")]));
  await act(async () => calls[0].resolve([opt("Stale")]));
  expect(optionNames()).toEqual(["Server One"]);
});

it("says No matches when the loader returns nothing", async () => {
  const { load, calls } = deferredLoader();
  const { user } = setup({ options: undefined, loadOptions: load });
  await user.type(input(), "z");
  await waitFor(() => expect(calls).toHaveLength(1));
  await act(async () => calls[0].resolve([]));
  expect(screen.getByRole("status").textContent).toBe("No matches");
});

it("keeps a loaded selection's label after the query changes", async () => {
  const { load, calls } = deferredLoader();
  const { user } = setup({ options: undefined, loadOptions: load });
  await user.type(input(), "a");
  await waitFor(() => expect(calls).toHaveLength(1));
  await act(async () => calls[0].resolve([opt("Alpha")]));
  await user.keyboard("{Enter}");
  expect(input().value).toBe("Alpha");
  await user.type(input(), "z");
  await waitFor(() => expect(calls).toHaveLength(2));
  await act(async () => calls[1].resolve([]));
  await user.keyboard("{Escape}");
  expect(input().value).toBe("Alpha");
});

it("shows a load error instead of the previous options", async () => {
  const { load, calls } = deferredLoader();
  const { user, onValueChange } = setup({
    options: undefined,
    loadOptions: load,
  });
  await user.type(input(), "a");
  await waitFor(() => expect(calls).toHaveLength(1));
  await act(async () => calls[0].resolve([opt("Server One")]));
  expect(optionNames()).toEqual(["Server One"]);
  await user.type(input(), "b");
  await waitFor(() => expect(calls).toHaveLength(2));
  await act(async () => calls[1].reject(new Error("boom")));
  expect(screen.getByRole("status").textContent).toBe("Could not load options");
  expect(screen.queryByRole("option", { name: "Server One" })).toBeNull();
  await user.keyboard("{Enter}");
  expect(onValueChange).not.toHaveBeenCalled();
});

it("keeps the label of an option from an earlier response", async () => {
  const { load, calls } = deferredLoader();
  const onValueChange = vi.fn();
  const view = renderV1(
    <Combobox
      aria-label="Model"
      loadOptions={load}
      onValueChange={onValueChange}
    />,
  );
  const { user } = view;
  await user.type(input(), "b");
  await waitFor(() => expect(calls).toHaveLength(1));
  await act(async () => calls[0].resolve([opt("Beta")]));
  await user.clear(input());
  await user.type(input(), "a");
  await waitFor(() => expect(calls).toHaveLength(2));
  await act(async () => calls[1].resolve([opt("Alpha")]));
  await user.keyboard("{Enter}");
  expect(onValueChange).toHaveBeenLastCalledWith("alpha", opt("Alpha"));
  await user.type(input(), "z");
  await waitFor(() => expect(calls).toHaveLength(3));
  await act(async () => calls[2].resolve([opt("Zeta")]));
  await user.keyboard("{Escape}");
  view.rerender(
    <Combobox aria-label="Model" loadOptions={load} value="beta" />,
  );
  expect(input().value).toBe("Beta");
});

it("shows a preset selectedOption before any load", () => {
  const { load } = deferredLoader();
  renderV1(
    <Combobox
      aria-label="Model"
      loadOptions={load}
      value="x"
      selectedOption={{ value: "x", label: "Saved" }}
    />,
  );
  expect(input().value).toBe("Saved");
  expect(load).not.toHaveBeenCalled();
});

it("renders a window of a 1,000-option list and filters it to one", async () => {
  stubLayout();
  const options = Array.from({ length: 1000 }, (_, i) => ({
    value: `v${i}`,
    label: `Option ${i}`,
  }));
  const started = performance.now();
  const { user } = setup({ options });
  await user.click(input());
  await user.keyboard("{ArrowDown}");
  const rows = screen.getAllByRole("option");
  expect(rows.length).toBeGreaterThan(0);
  expect(rows.length).toBeLessThan(60);
  await user.type(input(), "Option 999");
  expect(optionNames()).toEqual(["Option 999"]);
  expect(performance.now() - started).toBeLessThan(1000);
});

it("has no axe violations closed and open", async () => {
  const { user } = setup({ defaultValue: "claude" });
  await expectNoA11yViolations(document.body);
  await user.click(screen.getByRole("button", { name: "Show options" }));
  await expectNoA11yViolations(document.body);
});
