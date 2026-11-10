import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { Star } from "lucide-react";
import { expect, it, vi } from "vitest";
import type { SelectOption } from "./options";
import { Select } from "./Select";

const MODELS: readonly SelectOption[] = [
  { value: "claude", label: "Claude", leading: <Star aria-hidden /> },
  { value: "gemini", label: "Gemini", description: "Google" },
  { value: "grok", label: "Grok", disabled: true },
  { value: "gemma", label: "Gemma" },
  { value: "llama", label: "Llama" },
];

function trigger(): HTMLElement {
  // `hidden`: Radix hides everything outside the open list from the a11y tree.
  return screen.getByRole("combobox", { name: "Model", hidden: true });
}

function highlighted(): string | null | undefined {
  return document.querySelector('[role="option"][data-highlighted]')
    ?.textContent;
}

function setup(props: Partial<Parameters<typeof Select>[0]> = {}) {
  const onValueChange = vi.fn();
  const view = renderV1(
    <Select
      options={MODELS}
      placeholder="Pick a model"
      aria-label="Model"
      onValueChange={onValueChange}
      {...props}
    />,
  );
  return { ...view, onValueChange };
}

it("opens on click and lists every option by name", async () => {
  const { user } = setup();
  expect(trigger().getAttribute("aria-expanded")).toBe("false");
  expect(trigger().textContent).toBe("Pick a model");
  await user.click(trigger());
  expect(trigger().getAttribute("aria-expanded")).toBe("true");
  expect(trigger().getAttribute("data-state")).toBe("open");
  const names = screen
    .getAllByRole("option")
    .map((option) => option.textContent);
  expect(names).toEqual(["Claude", "GeminiGoogle", "Grok", "Gemma", "Llama"]);
  expect(screen.getByRole("option", { name: "Llama" })).toBeTruthy();
});

it("moves with ArrowDown, skips the disabled option and selects on Enter", async () => {
  const { user, onValueChange } = setup();
  await user.click(trigger());
  expect(highlighted()).toBe("Claude");
  await user.keyboard("{ArrowDown}");
  expect(highlighted()).toBe("GeminiGoogle");
  await user.keyboard("{ArrowDown}");
  expect(highlighted()).toBe("Gemma");
  await user.keyboard("{Enter}");
  expect(onValueChange).toHaveBeenCalledWith("gemma");
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(trigger().textContent).toBe("Gemma");
});

it("shows only the label, never the description, in the trigger", async () => {
  const { user } = setup();
  await user.click(trigger());
  await user.keyboard("{ArrowDown}{Enter}");
  expect(trigger().textContent).toBe("Gemini");
});

it("closes on Escape without changing the value", async () => {
  const { user, onValueChange } = setup({ defaultValue: "llama" });
  await user.click(trigger());
  await user.keyboard("{Home}{Escape}");
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(onValueChange).not.toHaveBeenCalled();
  expect(trigger().textContent).toBe("Llama");
});

it("jumps to the first and last option with Home and End", async () => {
  const { user } = setup({ defaultValue: "gemma" });
  await user.click(trigger());
  expect(highlighted()).toBe("Gemma");
  await user.keyboard("{End}");
  expect(highlighted()).toBe("Llama");
  await user.keyboard("{Home}");
  expect(highlighted()).toBe("Claude");
});

it("cycles type-ahead through the options starting with a repeated letter", async () => {
  const { user } = setup();
  await user.click(trigger());
  await user.keyboard("g");
  expect(highlighted()).toBe("GeminiGoogle");
  await user.keyboard("g");
  expect(highlighted()).toBe("Gemma");
  await user.keyboard("g");
  expect(highlighted()).toBe("GeminiGoogle");
});

it("does not select a disabled option", async () => {
  const { user, onValueChange } = setup();
  await user.click(trigger());
  const grok = screen.getByRole("option", { name: "Grok" });
  expect(grok.getAttribute("aria-disabled")).toBe("true");
  expect(grok.hasAttribute("data-disabled")).toBe(true);
  await user.click(grok);
  expect(onValueChange).not.toHaveBeenCalled();
});

it("marks the trigger invalid", () => {
  const { rerender } = setup();
  expect(trigger().hasAttribute("aria-invalid")).toBe(false);
  expect(trigger().hasAttribute("data-invalid")).toBe(false);
  rerender(
    <Select options={MODELS} aria-label="Model" placeholder="Pick" invalid />,
  );
  expect(trigger().getAttribute("aria-invalid")).toBe("true");
  expect(trigger().getAttribute("data-invalid")).toBe("");
});

it("disables the trigger", async () => {
  const { user } = setup({ disabled: true });
  expect((trigger() as HTMLButtonElement).disabled).toBe(true);
  await user.click(trigger());
  expect(screen.queryByRole("listbox")).toBeNull();
});

it("shows the placeholder for a value that matches no option", () => {
  setup({ value: "gpt-3" });
  expect(trigger().textContent).toBe("Pick a model");
  expect(trigger().hasAttribute("data-placeholder")).toBe(true);
});

it("shows the placeholder for a default value that matches no option", () => {
  setup({ defaultValue: "gpt-3" });
  expect(trigger().textContent).toBe("Pick a model");
  expect(trigger().hasAttribute("data-placeholder")).toBe(true);
});

it("passes id, className and the aria props to the trigger", () => {
  renderV1(
    <>
      <span id="model-label">Model</span>
      <span id="model-help">Used for extraction</span>
      <Select
        options={MODELS}
        id="model"
        className="extra"
        aria-labelledby="model-label"
        aria-describedby="model-help"
      />
    </>,
  );
  const button = screen.getByRole("combobox", { name: "Model" });
  expect(button.id).toBe("model");
  expect(button.className).toContain("extra");
  expect(button.getAttribute("aria-describedby")).toBe("model-help");
  expect(button.getAttribute("data-slot")).toBe("select-trigger");
});

it("shows the selected option's leading icon beside its label in the trigger", () => {
  const { rerender } = setup({ value: "gemma" });
  expect(trigger().querySelector("svg.lucide-star")).toBeNull();
  rerender(<Select options={MODELS} aria-label="Model" value="claude" />);
  expect(trigger().querySelector("svg.lucide-star")).not.toBeNull();
  expect(trigger().textContent).toBe("Claude");
});

it("lays the value out in a truncating flex row that leaves room for the chevron", () => {
  setup({ value: "claude" });
  const wrapper = trigger().querySelector('[data-slot="select-value"]');
  expect(wrapper?.parentElement).toBe(trigger());
  for (const name of [
    "ui:flex",
    "ui:min-w-0",
    "ui:flex-1",
    "ui:items-center",
    "ui:*:flex",
    "ui:*:min-w-0",
    "ui:*:flex-1",
    "ui:*:items-center",
    "ui:*:gap-1.5",
    "ui:*:truncate",
  ]) {
    expect(wrapper?.classList.contains(name), name).toBe(true);
  }
  // Radix drops SelectValue's className, so the wrapper's child variants
  // style the value element Radix renders.
  const value = wrapper?.firstElementChild as HTMLElement;
  expect(wrapper?.childElementCount).toBe(1);
  expect(value.getAttribute("data-slot")).toBe("select-value-text");
  expect(value.style.pointerEvents).toBe("none");
  const label = value.lastElementChild as HTMLElement;
  expect(label.textContent).toBe("Claude");
  expect(label.classList.contains("ui:truncate")).toBe(true);
  expect(label.classList.contains("ui:min-w-0")).toBe(true);
});

it("draws the check only on the selected option", async () => {
  const { user } = setup({ defaultValue: "gemma" });
  await user.click(trigger());
  const checks = document.querySelectorAll('[role="option"] svg.lucide-check');
  expect(checks).toHaveLength(1);
  expect(
    screen
      .getByRole("option", { name: "Gemma" })
      .querySelector("svg.lucide-check"),
  ).not.toBeNull();
});

it("keeps both height caps: max-h-80 on the list, the available height on the viewport", async () => {
  const { user } = setup();
  await user.click(trigger());
  const listbox = screen.getByRole("listbox");
  const viewport = document.querySelector("[data-radix-select-viewport]");
  expect(listbox.className).toContain("ui:max-h-80");
  expect(viewport?.className).toContain(
    "ui:max-h-(--radix-select-content-available-height)",
  );
});

it("shows a status row when there are no options", async () => {
  const { user } = setup({ options: [] });
  await user.click(trigger());
  expect(screen.getByRole("status").textContent).toBe("No options");
});

it("passes name and required to the native select a form submits", async () => {
  const { user } = renderV1(
    <form>
      <Select options={MODELS} aria-label="Model" name="model" required />
    </form>,
  );
  const native = document.querySelector<HTMLSelectElement>(
    'select[name="model"]',
  );
  expect(native).not.toBeNull();
  expect(native?.required).toBe(true);
  await user.click(trigger());
  await user.click(screen.getByRole("option", { name: "Gemma" }));
  expect(native?.value).toBe("gemma");
});
