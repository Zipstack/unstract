import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Copying an adapter's id off its card.
 *
 * The Agent-KV API makes the caller name their own `llm` / `lite_llm` /
 * `x2text` adapters by INSTANCE id, and that id was not in the product
 * anywhere: the card shows the name, and `id` was used only as a React key
 * and for edit/delete. The first person to try the API got
 * `Must be a valid UUID` and no way forward short of the network tab.
 *
 * Two things are worth pinning rather than eyeballing:
 *
 * 1. It copies `item.id` and NOT `item.adapter_id`. Both are on the row, both
 *    look like identifiers, and `adapter_id` is the provider descriptor
 *    (`anthropic|90ebd4cd-...`) shared by every instance of that provider —
 *    so the wrong one is copied happily and fails later, at submit, as
 *    "no such adapter in this organization".
 * 2. The handler is on the menu ENTRY. The dropdown opens on pointerdown and
 *    pins `pointer-events: none` on <body> while open, so a handler on the
 *    kebab trigger never fires — the trap Manage Users hit, where Edit looked
 *    like it did nothing.
 */
const copyToClipboard = vi.fn();

vi.mock("../../../hooks/useCopyToClipboard", () => ({
  useCopyToClipboard: () => copyToClipboard,
}));

const { ListOfItems } = await import("./ListOfItems.jsx");

const ROWS = [
  {
    id: "ff3f12e5-f119-44cb-9ecb-f35f16f87cbf",
    adapter_id: "anthropic|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203",
    adapter_name: "sonnet 4.6",
    adapter_type: "LLM",
  },
];

function openTheCardMenu(container) {
  // The trigger is the kebab SVG itself, carrying `aria-haspopup="menu"`.
  // Radix opens on POINTERDOWN, not click — firing only a click leaves the
  // menu shut and the entry unfindable.
  const trigger = container.querySelector('[aria-haspopup="menu"]');
  expect(trigger, "the card must still have a kebab menu").to.exist;
  fireEvent.pointerDown(
    trigger,
    new window.PointerEvent("pointerdown", { bubbles: true, button: 0 }),
  );
}

function renderList() {
  return render(
    <ListOfItems
      isLoading={false}
      tableRows={ROWS}
      setEditItemId={vi.fn()}
      handleDelete={vi.fn()}
      handleClick={vi.fn()}
    />,
  );
}

describe("ListOfItems — Copy ID", () => {
  beforeEach(() => {
    copyToClipboard.mockClear();
  });

  it("copies the instance id, not the provider descriptor", async () => {
    const { container } = renderList();

    openTheCardMenu(container);
    const entry = await screen.findByText("Copy ID");
    fireEvent.click(entry);

    await waitFor(() => expect(copyToClipboard).toHaveBeenCalled());
    const [value] = copyToClipboard.mock.calls[0];
    expect(value).toBe(ROWS[0].id);
    expect(value).not.toBe(ROWS[0].adapter_id);
  });
});
