import { fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The copy button's check icon claims the code is on the clipboard, so it must
 * only appear once the write has succeeded; a failed or impossible write is
 * reported as an error instead.
 */
const setAlertDetails = vi.fn();

vi.mock("../../../store/alert-store", () => ({
  useAlertStore: () => ({ setAlertDetails }),
}));

const { DisplayCode } = await import("./DisplayCode.jsx");

const renderOpen = () =>
  render(
    <DisplayCode
      isDialogOpen
      setDialogOpen={vi.fn()}
      url="https://example.test/api"
    />,
  );

const copyButton = () => document.querySelector(".copyCodeBtn");
const originalClipboard = navigator.clipboard;

const setClipboard = (value) =>
  Object.defineProperty(navigator, "clipboard", {
    value,
    configurable: true,
  });

describe("DisplayCode copy button", () => {
  beforeEach(() => {
    setAlertDetails.mockClear();
  });

  afterEach(() => {
    setClipboard(originalClipboard);
  });

  it("shows the copied state only after the write succeeds", async () => {
    setClipboard({ writeText: vi.fn(() => Promise.resolve()) });
    renderOpen();

    fireEvent.click(copyButton());

    await waitFor(() =>
      expect(document.querySelector(".copyCodeBtn")?.innerHTML).toMatch(
        /circle-check/,
      ),
    );
    expect(setAlertDetails).not.toHaveBeenCalled();
  });

  it("reports a rejected write and never shows the copied state", async () => {
    setClipboard({
      writeText: vi.fn(() => Promise.reject(new Error("denied"))),
    });
    renderOpen();

    fireEvent.click(copyButton());

    await waitFor(() =>
      expect(setAlertDetails).toHaveBeenCalledWith({
        type: "error",
        content: "Failed to copy: denied",
      }),
    );
    expect(copyButton().innerHTML).not.toMatch(/circle-check/);
  });

  it("reports a missing clipboard API instead of throwing", () => {
    setClipboard(undefined);
    renderOpen();

    fireEvent.click(copyButton());

    expect(setAlertDetails).toHaveBeenCalledWith({
      type: "error",
      content: "Clipboard not available in this browser",
    });
    expect(copyButton().innerHTML).not.toMatch(/circle-check/);
  });
});
