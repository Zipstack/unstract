import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Dropdown } from "@/components/ui/shims/antd-overlays";
import { ConfirmHost } from "./ConfirmHost";
import { ConfirmModal } from "./ConfirmModal";
import { resetConfirm } from "./confirmStore";

// The store is module-level, so a dialog left open by one test would leak
// `pointer-events: none` on <body> into the next.
afterEach(() => {
  cleanup();
  resetConfirm();
});

/**
 * The regression these cover: Delete in a prompt card's kebab menu did nothing
 * at all. `Modal.useModal()` kept the dialog in a hook rendered as a sibling of
 * the menu item, and Radix unmounts DropdownMenu content on click — so the
 * holder was destroyed in the same tick that asked it to open.
 */

function Harness({ children }) {
  return (
    <>
      {children}
      <ConfirmHost />
    </>
  );
}

describe("ConfirmModal", () => {
  it("opens the dialog from a plain trigger", async () => {
    render(
      <Harness>
        <ConfirmModal handleConfirm={vi.fn()} content="Gone forever.">
          Delete
        </ConfirmModal>
      </Harness>,
    );
    await userEvent.click(screen.getByText("Delete"));
    expect(await screen.findByText("Gone forever.")).toBeInTheDocument();
  });

  it("runs handleConfirm only after the dialog is confirmed", async () => {
    const onConfirm = vi.fn();
    render(
      <Harness>
        <ConfirmModal handleConfirm={onConfirm} content="Gone forever.">
          Delete
        </ConfirmModal>
      </Harness>,
    );
    await userEvent.click(screen.getByText("Delete"));
    expect(onConfirm).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("does not run handleConfirm when cancelled", async () => {
    const onConfirm = vi.fn();
    render(
      <Harness>
        <ConfirmModal handleConfirm={onConfirm} content="Gone forever.">
          Delete
        </ConfirmModal>
      </Harness>,
    );
    await userEvent.click(screen.getByText("Delete"));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onConfirm).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.queryByText("Gone forever.")).not.toBeInTheDocument(),
    );
  });

  /*
   * The actual bug. The trigger lives inside a dropdown that unmounts its own
   * content on click, so the dialog must be hosted outside that subtree.
   */
  it("still opens when its trigger is inside a dropdown that closes on click", async () => {
    const onConfirm = vi.fn();
    render(
      <Harness>
        <Dropdown
          menu={{
            items: [
              {
                key: "delete",
                label: (
                  <ConfirmModal
                    handleConfirm={onConfirm}
                    content="The prompt will be permanently deleted."
                  >
                    Delete
                  </ConfirmModal>
                ),
              },
            ],
          }}
        >
          <button type="button">Open menu</button>
        </Dropdown>
      </Harness>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
    await userEvent.click(await screen.findByText("Delete"));

    // The menu is gone, but the dialog survives it.
    expect(
      await screen.findByText("The prompt will be permanently deleted."),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  /*
   * Radix closes the menu on pointerdown anywhere in the item, so any part of
   * the row that is NOT the ConfirmModal is a dead zone: the menu dismisses
   * and the handler never runs. That is the "works sometimes" report — the
   * outcome depended on where in the row the pointer landed.
   */
  it("leaves no dead zone between the menu item and its confirm trigger", async () => {
    render(
      <Harness>
        <Dropdown
          menu={{
            items: [
              {
                key: "delete",
                label: (
                  <ConfirmModal handleConfirm={vi.fn()} content="Gone.">
                    Delete
                  </ConfirmModal>
                ),
              },
            ],
          }}
        >
          <button type="button">Open menu</button>
        </Dropdown>
      </Harness>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const item = await screen.findByRole("menuitem");
    const trigger = item.querySelector(".ant-space");

    // The item adds no padding of its own, and the padding it does apply is
    // pushed onto the trigger via `[&>*]` — so the whole row is the trigger
    // rather than a padded ring around it.
    expect(item.className).toContain("p-0");
    expect(trigger.className).toContain("w-full");
    const label = item.querySelector(".ant-dropdown-menu-title-content");
    expect(label.className).toContain("[&>*]:px-2");
    expect(label.className).toContain("[&>*]:py-1.5");
    expect(label.firstElementChild).toBe(trigger);
  });

  it("skips the dialog entirely when isDisabled", async () => {
    const onConfirm = vi.fn();
    render(
      <Harness>
        <ConfirmModal handleConfirm={onConfirm} isDisabled content="Nope.">
          Delete
        </ConfirmModal>
      </Harness>,
    );
    await userEvent.click(screen.getByText("Delete"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Nope.")).not.toBeInTheDocument();
  });
});
