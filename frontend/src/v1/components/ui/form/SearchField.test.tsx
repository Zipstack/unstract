import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Dialog } from "radix-ui";
import { type KeyboardEvent, useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { Field } from "./Field";
import { SearchField, type SearchFieldProps } from "./SearchField";

const cleanups: (() => void)[] = [];
afterEach(() => {
  for (const cleanup of cleanups.splice(0)) {
    cleanup();
  }
});

/** Counts the Escapes that bubble up to the document. */
function recordDocumentEscapes() {
  const escapes = vi.fn();
  const onKeyDown = (event: globalThis.KeyboardEvent) => {
    if (event.key === "Escape") {
      escapes();
    }
  };
  document.addEventListener("keydown", onKeyDown);
  cleanups.push(() => document.removeEventListener("keydown", onKeyDown));
  return escapes;
}

/** Renders the field and records the Escapes that bubble up to the document. */
function setup(props: SearchFieldProps = {}) {
  const parentEscape = recordDocumentEscapes();
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

/** A Radix dialog that follows the documented contract: skip dismissal while Escape would clear. */
function SearchDialog({
  onOpenChange,
}: {
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog.Root defaultOpen onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Content
          onEscapeKeyDown={(event) => {
            if (
              event.target instanceof Element &&
              event.target.closest("[data-escape-clears]")
            ) {
              event.preventDefault();
            }
          }}
        >
          <Dialog.Title>Find a document</Dialog.Title>
          <Dialog.Description>Search by name</Dialog.Description>
          <SearchField aria-label="Search" />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

it("inside a Radix dialog, Escape clears a value without closing, then closes when empty", async () => {
  const user = userEvent.setup();
  const onOpenChange = vi.fn();
  render(<SearchDialog onOpenChange={onOpenChange} />);
  const input = screen.getByLabelText("Search") as HTMLInputElement;
  await user.type(input, "invoice");

  await user.keyboard("{Escape}");
  expect(input.value).toBe("");
  expect(onOpenChange).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog")).toBeTruthy();

  await user.keyboard("{Escape}");
  expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
});

it("lets the caller's onKeyDown cancel the clear, and forwards onChange", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const onKeyDown = vi.fn((event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
    }
  });
  const { input } = setup({ onChange, onKeyDown });
  await user.type(input, "ab");
  expect(onChange).toHaveBeenCalledTimes(2);
  await user.keyboard("{Escape}");
  expect(onKeyDown).toHaveBeenLastCalledWith(
    expect.objectContaining({ key: "Escape" }),
  );
  expect(input.value).toBe("ab");
});

it("calls onValueChange when a controlled field's Clear button is used", async () => {
  const user = userEvent.setup();
  const onValueChange = vi.fn();
  render(
    <SearchField
      aria-label="Search"
      value="draft"
      onValueChange={onValueChange}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Clear search" }));
  expect(onValueChange).toHaveBeenCalledExactlyOnceWith("");
});

it("lets Escape through from a controlled field that has no onValueChange", () => {
  const parentEscape = recordDocumentEscapes();
  render(<SearchField aria-label="Search" value="fixed" readOnly />);
  fireEvent.keyDown(screen.getByLabelText("Search"), { key: "Escape" });
  expect(parentEscape).toHaveBeenCalledOnce();
});

it.each([
  ["disabled", { disabled: true }],
  ["read-only", { readOnly: true }],
])("does not clear inside a %s Field", (_, fieldProps) => {
  const parentEscape = recordDocumentEscapes();
  render(
    <Field label="Search" {...fieldProps}>
      <SearchField defaultValue="q" />
    </Field>,
  );
  const input = screen.getByLabelText("Search") as HTMLInputElement;
  fireEvent.keyDown(input, { key: "Escape" });
  expect(input.value).toBe("q");
  expect(parentEscape).toHaveBeenCalledOnce();
  expect(screen.queryByRole("button", { name: "Clear search" })).toBeNull();
});
