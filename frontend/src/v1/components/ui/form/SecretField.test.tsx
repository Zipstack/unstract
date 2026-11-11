import { screen } from "@testing-library/react";
import * as notify from "@v1/lib/notify";
import { renderV1 } from "@v1/test";
import type { JSX } from "react";
import { expect, it, vi } from "vitest";
import { Field } from "./Field";
import { SecretField } from "./SecretField";

// renderV1's userEvent installs a working clipboard on navigator; failures are
// simulated by spying on it after render (restored by restoreMocks).

const button = (name: string) =>
  screen.getByRole("button", { name }) as HTMLButtonElement;
const input = () => screen.getByLabelText("API key") as HTMLInputElement;

it("is masked by default and Reveal toggles the mask with aria-pressed", async () => {
  const { user } = renderV1(
    <SecretField aria-label="API key" defaultValue="sk-123" />,
  );
  expect(input().type).toBe("password");
  expect(button("Reveal").getAttribute("aria-pressed")).toBe("false");

  await user.click(button("Reveal"));
  expect(input().type).toBe("text");
  expect(button("Reveal").getAttribute("aria-pressed")).toBe("true");

  await user.click(button("Reveal"));
  expect(input().type).toBe("password");
});

it("masks a revealed value again when the field becomes disabled", async () => {
  const { user, rerender } = renderV1(
    <SecretField aria-label="API key" defaultValue="sk-123" />,
  );
  await user.click(button("Reveal"));
  expect(input().type).toBe("text");
  rerender(<SecretField aria-label="API key" defaultValue="sk-123" disabled />);
  expect(input().type).toBe("password");
  expect(button("Reveal").getAttribute("aria-pressed")).toBe("false");
});

it("copies the real value while masked and confirms through the toast", async () => {
  const success = vi.spyOn(notify.toast, "success");
  const onCopy = vi.fn();
  const { user } = renderV1(
    <SecretField aria-label="API key" defaultValue="sk-123" onCopy={onCopy} />,
  );
  await user.click(button("Copy"));
  await vi.waitFor(() => expect(onCopy).toHaveBeenCalledWith("copied"));
  await expect(navigator.clipboard.readText()).resolves.toBe("sk-123");
  expect(success).toHaveBeenCalledWith("Copied to clipboard");
});

it("reports a refused copy as an error toast, not a confirmation", async () => {
  const success = vi.spyOn(notify.toast, "success");
  const error = vi.spyOn(notify.toast, "error");
  const onCopy = vi.fn();
  const { user } = renderV1(
    <SecretField aria-label="API key" defaultValue="sk-123" onCopy={onCopy} />,
  );
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(
    new Error("denied"),
  );
  await user.click(button("Copy"));
  await vi.waitFor(() => expect(onCopy).toHaveBeenCalledWith("failed"));
  expect(error).toHaveBeenCalledWith("Could not copy", expect.anything());
  expect(success).not.toHaveBeenCalled();
});

it("reports a missing clipboard as unavailable, as CopyButton does", async () => {
  const error = vi.spyOn(notify.toast, "error");
  const onCopy = vi.fn();
  const { user } = renderV1(
    <SecretField aria-label="API key" defaultValue="sk-123" onCopy={onCopy} />,
  );
  vi.spyOn(navigator, "clipboard", "get").mockReturnValue(
    undefined as unknown as Clipboard,
  );
  await user.click(button("Copy"));
  await vi.waitFor(() => expect(onCopy).toHaveBeenCalledWith("unavailable"));
  expect(error).toHaveBeenCalledWith(
    "Copy is not available",
    expect.anything(),
  );
});

it("does not write an empty value; it says so and skips onCopy", async () => {
  const error = vi.spyOn(notify.toast, "error");
  const onCopy = vi.fn();
  const { user } = renderV1(
    <SecretField aria-label="API key" onCopy={onCopy} />,
  );
  const write = vi.spyOn(navigator.clipboard, "writeText");
  await user.click(button("Copy"));
  await vi.waitFor(() => expect(error).toHaveBeenCalledWith("Nothing to copy"));
  expect(write).not.toHaveBeenCalled();
  expect(onCopy).not.toHaveBeenCalled();
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
  renderV1(wrap(<SecretField aria-label="API key" value="sk-1" {...props} />));
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
  const onCopy = vi.fn();
  const { user } = renderV1(
    wrap(
      <SecretField
        aria-label="API key"
        value="sk-1"
        onCopy={onCopy}
        {...props}
      />,
    ),
  );
  expect(input().readOnly).toBe(true);
  await user.click(button("Reveal"));
  expect(input().type).toBe("text");
  await user.click(button("Copy"));
  await vi.waitFor(() => expect(onCopy).toHaveBeenCalledWith("copied"));
});

it("keeps password managers and spellcheck off, whatever the caller passes", () => {
  // Cast: the props type omits these, but a spread of untyped props could still carry them.
  const override = {
    autoComplete: "on",
    spellCheck: true,
    type: "text",
  } as object;
  renderV1(
    <SecretField aria-label="API key" defaultValue="sk-1" {...override} />,
  );
  expect(input().type).toBe("password");
  expect(input().autocomplete).toBe("new-password");
  expect(input().getAttribute("spellcheck")).toBe("false");
  expect(input().getAttribute("autocapitalize")).toBe("off");
  expect(input().hasAttribute("data-1p-ignore")).toBe(true);
  expect(input().getAttribute("data-lpignore")).toBe("true");
});
