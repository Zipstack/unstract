import { fireEvent, screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { Dialog } from "radix-ui";
import { type ChangeEvent, type KeyboardEvent, useState } from "react";
import { useForm } from "react-hook-form";
import { expect, it, onTestFinished, vi } from "vitest";
import { Field } from "./Field";
import { isEscapeClearTarget } from "./keyboard";
import { SearchField, type SearchFieldProps } from "./SearchField";

/** Counts the Escapes that bubble up to the document. */
function recordDocumentEscapes() {
  const escapes = vi.fn();
  const onKeyDown = (event: globalThis.KeyboardEvent) => {
    if (event.key === "Escape") {
      escapes();
    }
  };
  document.addEventListener("keydown", onKeyDown);
  onTestFinished(() => document.removeEventListener("keydown", onKeyDown));
  return escapes;
}

/** Renders the field and records the Escapes that bubble up to the document. */
function setup(props: SearchFieldProps = {}) {
  const parentEscape = recordDocumentEscapes();
  const { user } = renderV1(<SearchField aria-label="Search" {...props} />);
  return {
    user,
    parentEscape,
    input: screen.getByLabelText("Search") as HTMLInputElement,
  };
}

it("clears on Escape when it has a value, and keeps the Escape from bubbling", async () => {
  const onValueChange = vi.fn();
  const { user, input, parentEscape } = setup({ onValueChange });
  await user.type(input, "invoice");
  await user.keyboard("{Escape}");
  expect(input.value).toBe("");
  expect(onValueChange).toHaveBeenLastCalledWith("");
  expect(parentEscape).not.toHaveBeenCalled();
  expect(document.activeElement).toBe(input);
});

it("lets Escape bubble when the field is empty, so a dialog can close", async () => {
  const { user, input, parentEscape } = setup();
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
  const { user, input } = setup();
  expect(input.hasAttribute("data-escape-clears")).toBe(false);
  await user.type(input, "a");
  expect(input.hasAttribute("data-escape-clears")).toBe(true);
});

it("clears a controlled field through onValueChange", async () => {
  function Controlled() {
    const [value, setValue] = useState("draft");
    return (
      <SearchField aria-label="Search" value={value} onValueChange={setValue} />
    );
  }
  const { user } = renderV1(<Controlled />);
  const input = screen.getByLabelText("Search") as HTMLInputElement;
  await user.click(input);
  await user.keyboard("{Escape}");
  expect(input.value).toBe("");
});

it("offers a named Clear button while it has a value, and refocuses the field", async () => {
  const { user, input } = setup();
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
  onKeyDown,
}: {
  onOpenChange: (open: boolean) => void;
  onKeyDown?: SearchFieldProps["onKeyDown"];
}) {
  return (
    <Dialog.Root defaultOpen onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Content
          onEscapeKeyDown={(event) => {
            if (isEscapeClearTarget(event)) {
              event.preventDefault();
            }
          }}
        >
          <Dialog.Title>Find a document</Dialog.Title>
          <Dialog.Description>Search by name</Dialog.Description>
          <SearchField aria-label="Search" onKeyDown={onKeyDown} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

it("inside a Radix dialog, Escape clears a value without closing, then closes when empty", async () => {
  const onOpenChange = vi.fn();
  const { user } = renderV1(<SearchDialog onOpenChange={onOpenChange} />);
  const input = screen.getByLabelText("Search") as HTMLInputElement;
  await user.type(input, "invoice");

  await user.keyboard("{Escape}");
  expect(input.value).toBe("");
  expect(onOpenChange).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog")).toBeTruthy();

  await user.keyboard("{Escape}");
  expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
});

it("inside a Radix dialog, the caller's onKeyDown can still cancel the clear", async () => {
  const onOpenChange = vi.fn();
  const { user } = renderV1(
    <SearchDialog
      onOpenChange={onOpenChange}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
        }
      }}
    />,
  );
  const input = screen.getByLabelText("Search") as HTMLInputElement;
  await user.type(input, "invoice");
  await user.keyboard("{Escape}");
  expect(input.value).toBe("invoice");
  expect(onOpenChange).not.toHaveBeenCalled();
});

it("returns an uncontrolled field to its defaultValue when its form resets", async () => {
  const { user } = renderV1(
    <form>
      <SearchField aria-label="Search" defaultValue="draft" />
    </form>,
  );
  const input = screen.getByLabelText("Search") as HTMLInputElement;
  await user.type(input, " edited");
  expect(input.value).toBe("draft edited");
  fireEvent.reset(input.form as HTMLFormElement);
  await vi.waitFor(() => expect(input.value).toBe("draft"));
});

it("keeps the text when the form cancels its reset", async () => {
  const { user } = renderV1(
    <form onReset={(event) => event.preventDefault()}>
      <SearchField aria-label="Search" defaultValue="draft" />
    </form>,
  );
  const input = screen.getByLabelText("Search") as HTMLInputElement;
  await user.type(input, " edited");
  fireEvent.reset(input.form as HTMLFormElement);
  await new Promise((resolve) => setTimeout(resolve, 10));
  expect(input.value).toBe("draft edited");
});

it("keeps its own change handler when a caller spreads an onChange", async () => {
  // The react-hook-form pattern: `<SearchField {...field} />`. onChange is not
  // in the type, but a JSX spread is not checked for excess props.
  const spread = { onChange: vi.fn() } as Partial<SearchFieldProps>;
  const onValueChange = vi.fn();
  const { user } = renderV1(
    <SearchField
      aria-label="Search"
      onValueChange={onValueChange}
      {...spread}
    />,
  );
  const input = screen.getByLabelText("Search") as HTMLInputElement;
  await user.type(input, "ab");
  expect(input.value).toBe("ab");
  expect(onValueChange.mock.calls).toEqual([["a"], ["ab"]]);
  await user.keyboard("{Escape}");
  expect(input.value).toBe("");
});

it("types, clears and escapes through a spread { value, onChange } with no onValueChange", async () => {
  // `<SearchField {...field} />` from useController.
  function Controlled() {
    const [value, setValue] = useState("");
    const field = {
      value,
      onChange: (event: ChangeEvent<HTMLInputElement>) =>
        setValue(event.target.value),
    } as Partial<SearchFieldProps>;
    return <SearchField aria-label="Search" {...field} />;
  }
  const { user } = renderV1(<Controlled />);
  const input = screen.getByLabelText("Search") as HTMLInputElement;
  await user.type(input, "ab");
  expect(input.value).toBe("ab");
  await user.click(screen.getByRole("button", { name: "Clear search" }));
  expect(input.value).toBe("");
  await user.type(input, "cd");
  await user.keyboard("{Escape}");
  expect(input.value).toBe("");
});

it("reports typing and clearing to react-hook-form through a register() spread", async () => {
  function Form() {
    const { register, watch } = useForm({ defaultValues: { q: "" } });
    return (
      <>
        <SearchField aria-label="Search" {...register("q")} />
        <output aria-label="Watched">{watch("q")}</output>
      </>
    );
  }
  const { user } = renderV1(<Form />);
  const watched = screen.getByLabelText("Watched");
  await user.type(screen.getByLabelText("Search"), "ab");
  expect(watched.textContent).toBe("ab");
  await user.click(screen.getByRole("button", { name: "Clear search" }));
  expect(watched.textContent).toBe("");
});

it("lets the caller's onKeyDown cancel the clear, and reports typing through onValueChange", async () => {
  const onValueChange = vi.fn();
  const onKeyDown = vi.fn((event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
    }
  });
  const { user, input } = setup({ onValueChange, onKeyDown });
  await user.type(input, "ab");
  expect(onValueChange.mock.calls).toEqual([["a"], ["ab"]]);
  await user.keyboard("{Escape}");
  expect(onKeyDown).toHaveBeenLastCalledWith(
    expect.objectContaining({ key: "Escape" }),
  );
  expect(input.value).toBe("ab");
});

it("calls onValueChange when a controlled field's Clear button is used", async () => {
  const onValueChange = vi.fn();
  const { user } = renderV1(
    <SearchField
      aria-label="Search"
      value="draft"
      onValueChange={onValueChange}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Clear search" }));
  expect(onValueChange).toHaveBeenCalledExactlyOnceWith("");
});

it("lets Escape through from a controlled field that has no onValueChange, without the native clear", () => {
  const parentEscape = recordDocumentEscapes();
  renderV1(<SearchField aria-label="Search" value="fixed" />);
  const notPrevented = fireEvent.keyDown(screen.getByLabelText("Search"), {
    key: "Escape",
  });
  expect(parentEscape).toHaveBeenCalledOnce();
  // false: default prevented, so the browser's own search clear does not run.
  expect(notPrevented).toBe(false);
});

it("leaves onChange out of the type, so onValueChange is the documented API", () => {
  // @ts-expect-error onChange is not a SearchField prop.
  const props: SearchFieldProps = { onChange: () => undefined };
  expect(props).toBeDefined();
});

it("leaves the native Escape alone on an empty field", () => {
  renderV1(<SearchField aria-label="Search" />);
  expect(
    fireEvent.keyDown(screen.getByLabelText("Search"), { key: "Escape" }),
  ).toBe(true);
});

it.each([
  ["disabled", { disabled: true }],
  ["read-only", { readOnly: true }],
])("does not clear inside a %s Field", (_, fieldProps) => {
  const parentEscape = recordDocumentEscapes();
  renderV1(
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
