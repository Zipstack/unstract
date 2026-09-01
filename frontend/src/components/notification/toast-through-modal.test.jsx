import fs from "node:fs";
import path from "node:path";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { DismissableLayer } from "radix-ui/internal";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Modal } from "@/components/ui/shims/antd-overlays";
import { Toaster } from "@/components/ui/sonner";

/**
 * A toast raised BY an open modal has to stay usable THROUGH it.
 *
 * Reported against the Workflows page: "New Workflow" with a duplicate name
 * toasts the backend error and the toast's close button then does nothing.
 * Two independent mechanisms conspire, so both halves are pinned here:
 *
 *  1. Radix sets `pointer-events: none` on <body> for a modal Dialog. Sonner's
 *     viewport is an ordinary body-level element, so it inherits that and the
 *     toasts stop taking clicks at all. Fixed by `[data-sonner-toaster]` in
 *     index.css — asserted statically, since vitest runs with `css: false`.
 *  2. Once the clicks land, Radix reads them as an interaction OUTSIDE the
 *     dialog and dismisses it — closing the form the user was mid-way through
 *     correcting. Fixed by the DismissableLayer.Branch wrap in App.jsx.
 */

function Harness({ onCancel }) {
  return (
    <>
      <button type="button" data-testid="outside">
        elsewhere on the page
      </button>
      <Modal open title="New Workflow" onCancel={onCancel} footer={null}>
        <p>workflow form</p>
      </Modal>
      <DismissableLayer.Branch>
        <Toaster position="top-right" offset={56} closeButton richColors />
      </DismissableLayer.Branch>
    </>
  );
}

async function openModalWithToast(onCancel) {
  render(<Harness onCancel={onCancel} />);
  await screen.findByText("workflow form");
  act(() => {
    toast.error("workflow_name: A workflow with this name already exists.");
  });
  await screen.findByText(
    "workflow_name: A workflow with this name already exists.",
  );
  // Radix arms its outside-pointerdown listener in a queued task; without
  // waiting for it the "outside" control below passes vacuously.
  await waitFor(() => {
    expect(document.body.style.pointerEvents).toBe("none");
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("toast stack raised by an open modal", () => {
  afterEach(() => {
    act(() => {
      toast.dismiss();
    });
    document.body.style.pointerEvents = "";
  });

  it("keeps the dialog open when its own toast is dismissed", async () => {
    const onCancel = vi.fn();
    await openModalWithToast(onCancel);

    const closeToast = screen.getByLabelText("Close toast");
    fireEvent.pointerDown(closeToast, { button: 0 });
    fireEvent.click(closeToast);

    expect(onCancel).not.toHaveBeenCalled();
    expect(screen.getByText("workflow form")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.queryByText(
          "workflow_name: A workflow with this name already exists.",
        ),
      ).not.toBeInTheDocument();
    });
  });

  it("still closes on a genuine click outside the dialog", async () => {
    const onCancel = vi.fn();
    await openModalWithToast(onCancel);

    // Dialog runs with `deferPointerDownOutside`, so it is the CLICK that
    // dismisses, not the pointerdown — fire the pair the toast case fires.
    const outside = screen.getByTestId("outside");
    fireEvent.pointerDown(outside, { button: 0 });
    fireEvent.click(outside);

    await waitFor(() => {
      expect(onCancel).toHaveBeenCalled();
    });
  });

  it("re-enables pointer events on sonner's viewport", () => {
    const css = fs.readFileSync(
      path.resolve(import.meta.dirname, "../../index.css"),
      "utf-8",
    );
    const rule = css.match(/\[data-sonner-toaster\]\s*\{([^}]*)\}/);

    expect(
      rule,
      "index.css must re-enable pointer events on the toaster",
    ).not.toBeNull();
    expect(rule[1]).toMatch(/pointer-events:\s*auto/);
  });
});
