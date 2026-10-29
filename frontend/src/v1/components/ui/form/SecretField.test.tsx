import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { JSX } from "react";
import { expect, it, vi } from "vitest";
import { Field } from "./Field";
import { SecretField } from "./SecretField";

/** userEvent.setup() installs its own clipboard; replace it after setup. */
function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
}

const button = (name: string) =>
  screen.getByRole("button", { name }) as HTMLButtonElement;

it("is masked by default and Reveal toggles the mask with aria-pressed", async () => {
  const user = userEvent.setup();
  render(
    <SecretField
      aria-label="API key"
      defaultValue="sk-123"
      onCopyResult={vi.fn()}
    />,
  );
  const input = screen.getByLabelText("API key") as HTMLInputElement;
  expect(input.type).toBe("password");
  expect(button("Reveal").getAttribute("aria-pressed")).toBe("false");

  await user.click(button("Reveal"));
  expect(input.type).toBe("text");
  expect(button("Reveal").getAttribute("aria-pressed")).toBe("true");

  await user.click(button("Reveal"));
  expect(input.type).toBe("password");
});

it("copies the real value while masked and confirms through the toast callback", async () => {
  const user = userEvent.setup();
  const writeText = vi.fn(() => Promise.resolve());
  stubClipboard(writeText);
  const onCopyResult = vi.fn();
  render(
    <SecretField
      aria-label="API key"
      defaultValue="sk-123"
      onCopyResult={onCopyResult}
    />,
  );
  await user.click(button("Copy"));
  expect(writeText).toHaveBeenCalledExactlyOnceWith("sk-123");
  expect(onCopyResult).toHaveBeenCalledExactlyOnceWith({ status: "copied" });
});

it("reports a failed copy instead of confirming it", async () => {
  const user = userEvent.setup();
  const error = new Error("denied");
  stubClipboard(() => Promise.reject(error));
  const onCopyResult = vi.fn();
  render(
    <SecretField
      aria-label="API key"
      defaultValue="sk-123"
      onCopyResult={onCopyResult}
    />,
  );
  await user.click(button("Copy"));
  expect(onCopyResult).toHaveBeenCalledExactlyOnceWith({
    status: "failed",
    error,
  });
});

it("does not report a throwing result handler as a failed copy", async () => {
  const user = userEvent.setup();
  stubClipboard(() => Promise.resolve());
  const handlerError = new Error("toast broke");
  const onCopyResult = vi.fn(() => {
    throw handlerError;
  });
  // The handler's error must surface on its own, not be folded into a result.
  const unhandled: unknown[] = [];
  const onUnhandled = (reason: unknown) => unhandled.push(reason);
  process.on("unhandledRejection", onUnhandled);
  try {
    render(
      <SecretField
        aria-label="API key"
        defaultValue="sk-123"
        onCopyResult={onCopyResult}
      />,
    );
    await user.click(button("Copy"));
    await new Promise((resolve) => setTimeout(resolve, 10));
  } finally {
    process.off("unhandledRejection", onUnhandled);
  }
  expect(onCopyResult).toHaveBeenCalledExactlyOnceWith({ status: "copied" });
  expect(unhandled).toEqual([handlerError]);
});

it("does not write an empty value and reports it as empty", async () => {
  const user = userEvent.setup();
  const writeText = vi.fn(() => Promise.resolve());
  stubClipboard(writeText);
  const onCopyResult = vi.fn();
  render(<SecretField aria-label="API key" onCopyResult={onCopyResult} />);
  await user.click(button("Copy"));
  expect(writeText).not.toHaveBeenCalled();
  expect(onCopyResult).toHaveBeenCalledExactlyOnceWith({ status: "empty" });
});

it.each([
  ["prop", (node: JSX.Element) => node, { disabled: true }],
  [
    "Field",
    (node: JSX.Element) => (
      <Field label="API key" disabled>
        {node}
      </Field>
    ),
    {},
  ],
])("disables Reveal and Copy when disabled by %s", (_, wrap, props) => {
  render(
    wrap(
      <SecretField
        aria-label="API key"
        value="sk-1"
        onCopyResult={vi.fn()}
        {...props}
      />,
    ),
  );
  expect(button("Reveal").disabled).toBe(true);
  expect(button("Copy").disabled).toBe(true);
});

it.each([
  ["prop", (node: JSX.Element) => node, { readOnly: true }],
  [
    "Field",
    (node: JSX.Element) => (
      <Field label="API key" readOnly>
        {node}
      </Field>
    ),
    {},
  ],
])("keeps Reveal and Copy usable when read-only by %s", async (_, wrap, props) => {
  const user = userEvent.setup();
  stubClipboard(() => Promise.resolve());
  const onCopyResult = vi.fn();
  render(
    wrap(
      <SecretField
        aria-label="API key"
        value="sk-1"
        onCopyResult={onCopyResult}
        {...props}
      />,
    ),
  );
  const input = screen.getByLabelText("API key") as HTMLInputElement;
  expect(input.readOnly).toBe(true);
  await user.click(button("Reveal"));
  expect(input.type).toBe("text");
  await user.click(button("Copy"));
  expect(onCopyResult).toHaveBeenCalledExactlyOnceWith({ status: "copied" });
});

it("keeps password managers and spellcheck off, whatever the caller passes", () => {
  // Cast: the props type omits these, but a spread of untyped props could still carry them.
  const override = {
    autoComplete: "on",
    spellCheck: true,
    type: "text",
  } as object;
  render(
    <SecretField
      aria-label="API key"
      defaultValue="sk-1"
      onCopyResult={vi.fn()}
      {...override}
    />,
  );
  const input = screen.getByLabelText("API key") as HTMLInputElement;
  expect(input.type).toBe("password");
  expect(input.autocomplete).toBe("new-password");
  expect(input.getAttribute("spellcheck")).toBe("false");
  expect(input.getAttribute("autocapitalize")).toBe("off");
  expect(input.hasAttribute("data-1p-ignore")).toBe(true);
  expect(input.getAttribute("data-lpignore")).toBe("true");
});
