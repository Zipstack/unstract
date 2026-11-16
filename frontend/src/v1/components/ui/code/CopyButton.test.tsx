import { screen, waitFor } from "@testing-library/react";
import * as notify from "@v1/lib/notify";
import { renderV1 } from "@v1/test";
import { act } from "react";
import { expect, it, vi } from "vitest";
import { COPY_FEEDBACK_MS, CopyButton } from "./CopyButton";

// renderV1's userEvent installs a working clipboard on navigator; failures
// are simulated by spying on it after render.

it("copies, confirms through the toast and swaps to a check", async () => {
  const success = vi.spyOn(notify.toast, "success");
  const onCopy = vi.fn();
  const { user } = renderV1(
    <CopyButton text="secret" label="Copy key" onCopy={onCopy} />,
  );
  const button = screen.getByRole("button", { name: "Copy key" });
  await user.click(button);
  await waitFor(() => expect(onCopy).toHaveBeenCalledWith("copied"));
  await expect(navigator.clipboard.readText()).resolves.toBe("secret");
  expect(success).toHaveBeenCalledWith("Copied to clipboard");
  expect(button.getAttribute("data-state")).toBe("copied");
});

it("reads a function at click time", async () => {
  let value = "first";
  const onCopy = vi.fn();
  const { user } = renderV1(<CopyButton text={() => value} onCopy={onCopy} />);
  value = "second";
  await user.click(screen.getByRole("button", { name: "Copy" }));
  await waitFor(() => expect(onCopy).toHaveBeenCalled());
  await expect(navigator.clipboard.readText()).resolves.toBe("second");
});

it("reports a blocked copy as an error toast and inline", async () => {
  const error = vi.spyOn(notify.toast, "error");
  const { user } = renderV1(
    <CopyButton text="x" label="Copy code" showLabel />,
  );
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(
    new Error("denied"),
  );
  await user.click(screen.getByRole("button", { name: "Copy code" }));
  await waitFor(() =>
    expect(screen.getByRole("button").textContent).toBe("Copy failed"),
  );
  expect(error).toHaveBeenCalledWith("Could not copy", expect.anything());
});

it("reports a missing clipboard as unavailable", async () => {
  const error = vi.spyOn(notify.toast, "error");
  const { user } = renderV1(<CopyButton text="x" />);
  vi.spyOn(navigator, "clipboard", "get").mockReturnValue(
    undefined as unknown as Clipboard,
  );
  await user.click(screen.getByRole("button", { name: "Copy" }));
  await waitFor(() =>
    expect(screen.getByRole("button").getAttribute("data-state")).toBe(
      "unavailable",
    ),
  );
  expect(error).toHaveBeenCalledWith(
    "Copy is not available",
    expect.anything(),
  );
});

it("without a toast, announces the result once in a live region, then resets", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const success = vi.spyOn(notify.toast, "success");
  const { user } = renderV1(<CopyButton text="x" toastOnCopy={false} />, {
    userEventOptions: { advanceTimers: vi.advanceTimersByTime },
  });
  await user.click(screen.getByRole("button", { name: "Copy" }));
  await waitFor(() =>
    expect(screen.getByRole("status").textContent).toBe("Copied"),
  );
  expect(success).not.toHaveBeenCalled();
  act(() => {
    vi.advanceTimersByTime(COPY_FEEDBACK_MS);
  });
  expect(screen.getByRole("status").textContent).toBe("");
  expect(screen.getByRole("button").getAttribute("data-state")).toBe("idle");
});

it("works from the keyboard and can be disabled", async () => {
  const onCopy = vi.fn();
  const { user, rerender } = renderV1(<CopyButton text="x" onCopy={onCopy} />);
  await user.tab();
  await user.keyboard("{Enter}");
  await waitFor(() => expect(onCopy).toHaveBeenCalledOnce());
  rerender(<CopyButton text="x" disabled />);
  expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
});

it("leaves no timer behind when it unmounts while the clipboard is busy", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    const onCopy = vi.fn();
    const { user, unmount } = renderV1(
      <CopyButton text="x" onCopy={onCopy} />,
      {
        userEventOptions: { advanceTimers: vi.advanceTimersByTime },
      },
    );
    let finish: () => void = () => undefined;
    vi.spyOn(navigator.clipboard, "writeText").mockReturnValue(
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
    );
    await user.click(screen.getByRole("button", { name: "Copy" }));
    unmount();
    await act(async () => {
      finish();
    });
    expect(onCopy).toHaveBeenCalledWith("copied");
    expect(vi.getTimerCount()).toBe(0);
  } finally {
    vi.useRealTimers();
  }
});
