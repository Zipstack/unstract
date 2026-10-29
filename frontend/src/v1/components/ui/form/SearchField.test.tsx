import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { SearchField, type SearchFieldProps } from "./SearchField";

const cleanups: (() => void)[] = [];
afterEach(() => {
  for (const cleanup of cleanups.splice(0)) {
    cleanup();
  }
});

/** Renders the field and records the Escapes that bubble up to the document. */
function setup(props: SearchFieldProps = {}) {
  const parentEscape = vi.fn();
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      parentEscape();
    }
  };
  document.addEventListener("keydown", onKeyDown);
  cleanups.push(() => document.removeEventListener("keydown", onKeyDown));
  render(<SearchField aria-label="Search" {...props} />);
  return {
    parentEscape,
    input: screen.getByLabelText("Search") as HTMLInputElement,
  };
}

it("clears on Escape when it has a value, and keeps the Escape from bubbling", async () => {
  const user = userEvent.setup();
  const onValueChange = vi.fn();
  const { input, parentEscape } = setup({ onValueChange });
  await user.type(input, "invoice");
  await user.keyboard("{Escape}");
  expect(input.value).toBe("");
  expect(onValueChange).toHaveBeenLastCalledWith("");
  expect(parentEscape).not.toHaveBeenCalled();
  expect(document.activeElement).toBe(input);
});

it("lets Escape bubble when the field is empty, so a dialog can close", async () => {
  const user = userEvent.setup();
  const { input, parentEscape } = setup();
  await user.click(input);
  await user.keyboard("{Escape}");
  expect(parentEscape).toHaveBeenCalledOnce();
});

it("lets Escape bubble from a read-only field with a value", () => {
  const { input, parentEscape } = setup({ defaultValue: "x", readOnly: true });
  fireEvent.keyDown(input, { key: "Escape" });
  expect(input.value).toBe("x");
  expect(parentEscape).toHaveBeenCalledOnce();
});

it("does not clear on an Escape that cancels an IME composition", () => {
  const { input } = setup({ defaultValue: "かな" });
  fireEvent.keyDown(input, { key: "Escape", isComposing: true });
  expect(input.value).toBe("かな");
});

it("marks the control while Escape would clear it", async () => {
  const user = userEvent.setup();
  const { input } = setup();
  expect(input.hasAttribute("data-escape-clears")).toBe(false);
  await user.type(input, "a");
  expect(input.hasAttribute("data-escape-clears")).toBe(true);
});

it("clears a controlled field through onValueChange", async () => {
  const user = userEvent.setup();
  function Controlled() {
    const [value, setValue] = useState("draft");
    return (
      <SearchField aria-label="Search" value={value} onValueChange={setValue} />
    );
  }
  render(<Controlled />);
  const input = screen.getByLabelText("Search") as HTMLInputElement;
  await user.click(input);
  await user.keyboard("{Escape}");
  expect(input.value).toBe("");
});

it("offers a named Clear button while it has a value, and refocuses the field", async () => {
  const user = userEvent.setup();
  const { input } = setup();
  expect(screen.queryByRole("button", { name: "Clear search" })).toBeNull();
  await user.type(input, "abc");
  await user.click(screen.getByRole("button", { name: "Clear search" }));
  expect(input.value).toBe("");
  expect(document.activeElement).toBe(input);
});

it("is a searchbox", () => {
  setup();
  expect(screen.getByRole("searchbox", { name: "Search" })).toBeTruthy();
});
