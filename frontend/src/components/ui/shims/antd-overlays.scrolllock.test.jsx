import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Modal } from "@/components/ui/shims/antd-overlays";

/**
 * P2-02 / P0-12: `body { overflow: hidden }` vs Radix's scroll-lock.
 *
 * index.css sets `overflow: hidden` on body permanently (the app is a fixed
 * full-height shell). Radix ALSO sets `overflow: hidden` on body while a
 * dialog is open, and restores the previous value on close. The risk flagged
 * in P0-12 was that Radix could restore the wrong value — leaving body
 * scrollable after a dialog closes, which would break the app shell layout.
 *
 * These tests pin the invariant that actually matters: body overflow must be
 * hidden before, during, AND after a dialog's lifecycle.
 */

function bodyOverflow() {
  return (
    document.body.style.overflow ||
    getComputedStyle(document.body).overflow ||
    ""
  );
}

describe("dialog scroll-lock vs the app shell's body overflow (P2-02)", () => {
  afterEach(() => {
    document.body.style.overflow = "";
  });

  it("leaves body overflow hidden after a dialog opens and closes", async () => {
    // Reproduce the app shell: index.css pins body overflow hidden.
    document.body.style.overflow = "hidden";

    const { rerender } = render(<Modal open={false}>body content</Modal>);
    expect(bodyOverflow()).toBe("hidden");

    rerender(<Modal open>body content</Modal>);
    await waitFor(() =>
      expect(screen.getByText("body content")).toBeInTheDocument(),
    );
    // Radix locks scroll while open; the shell wanted it hidden anyway.
    expect(bodyOverflow()).toBe("hidden");

    rerender(<Modal open={false}>body content</Modal>);
    await waitFor(() =>
      expect(screen.queryByText("body content")).not.toBeInTheDocument(),
    );

    // The regression this guards: Radix restoring "" or "visible" here would
    // make the fixed app shell scrollable.
    expect(bodyOverflow()).toBe("hidden");
  });

  it("survives two open/close cycles without leaking overflow state", async () => {
    document.body.style.overflow = "hidden";
    const { rerender } = render(<Modal open={false}>cycle</Modal>);

    for (let i = 0; i < 2; i++) {
      rerender(<Modal open>cycle</Modal>);
      await waitFor(() => screen.getByText("cycle"));
      rerender(<Modal open={false}>cycle</Modal>);
      await waitFor(() =>
        expect(screen.queryByText("cycle")).not.toBeInTheDocument(),
      );
      expect(bodyOverflow()).toBe("hidden");
    }
  });

  it("restores the original value when the shell did NOT pin overflow", async () => {
    // Sanity check the other direction: on a page that never set overflow,
    // Radix must not leave it hidden after close.
    document.body.style.overflow = "";
    const { rerender } = render(<Modal open>free</Modal>);
    await waitFor(() => screen.getByText("free"));

    rerender(<Modal open={false}>free</Modal>);
    await waitFor(() =>
      expect(screen.queryByText("free")).not.toBeInTheDocument(),
    );
    expect(document.body.style.overflow).not.toBe("hidden");
  });
});
