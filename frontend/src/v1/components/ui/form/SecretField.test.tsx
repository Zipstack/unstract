import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { SecretField } from "./SecretField";

/** userEvent.setup() installs its own clipboard; replace it after setup. */
function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
}

it("is masked by default and Reveal toggles the mask with aria-pressed", async () => {
  const user = userEvent.setup();
  render(<SecretField aria-label="API key" defaultValue="sk-123" />);
  const input = screen.getByLabelText("API key") as HTMLInputElement;
  const reveal = screen.getByRole("button", { name: "Reveal" });
  expect(input.type).toBe("password");
  expect(reveal.getAttribute("aria-pressed")).toBe("false");

  await user.click(reveal);
  expect(input.type).toBe("text");
  expect(reveal.getAttribute("aria-pressed")).toBe("true");

  await user.click(reveal);
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
  await user.click(screen.getByRole("button", { name: "Copy" }));
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
  await user.click(screen.getByRole("button", { name: "Copy" }));
  expect(onCopyResult).toHaveBeenCalledExactlyOnceWith({
    status: "failed",
    error,
  });
});

it("still reveals and copies when read-only, and disables both when disabled", () => {
  const { rerender } = render(
    <SecretField aria-label="API key" value="sk-1" readOnly />,
  );
  for (const name of ["Reveal", "Copy"]) {
    expect(
      (screen.getByRole("button", { name }) as HTMLButtonElement).disabled,
    ).toBe(false);
  }
  rerender(<SecretField aria-label="API key" value="sk-1" disabled readOnly />);
  for (const name of ["Reveal", "Copy"]) {
    expect(
      (screen.getByRole("button", { name }) as HTMLButtonElement).disabled,
    ).toBe(true);
  }
});
