import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ACTION_ICONS } from "@v1/lib/icons";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from "./ContextMenu";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "./DropdownMenu";
import { MenuButton, MenuIconButton } from "./MenuTrigger";
import {
  groupActions,
  type MenuAction,
  RowActionMenu,
  RowContextMenu,
} from "./RowActionMenu";

const focused = () => document.activeElement as HTMLElement;
const focusedName = () =>
  focused().querySelector(".ui\\:truncate")?.textContent ??
  focused().textContent;

function renderMenu(onSelect = vi.fn()) {
  render(
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <MenuButton>Actions</MenuButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem
          icon={ACTION_ICONS.run}
          shortcut="⌘↵"
          onSelect={onSelect}
        >
          Run workflow
        </DropdownMenuItem>
        <DropdownMenuItem disabled>Deploy</DropdownMenuItem>
        <DropdownMenuItem loading onSelect={onSelect}>
          Export
        </DropdownMenuItem>
        <DropdownMenuItem description="Files picked up by earlier runs">
          View file history
        </DropdownMenuItem>
        <DropdownMenuSub>
          <DropdownMenuSubTrigger icon={ACTION_ICONS.share}>
            Share
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent>
            <DropdownMenuItem>Copy link</DropdownMenuItem>
            <DropdownMenuItem>Invite people</DropdownMenuItem>
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <DropdownMenuSeparator />
        <DropdownMenuItem destructive icon={ACTION_ICONS.delete}>
          Clear history
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>,
  );
  return onSelect;
}

async function openWithKeyboard() {
  const user = userEvent.setup();
  await user.tab();
  await user.keyboard("{Enter}");
  return user;
}

describe("DropdownMenu", () => {
  it("opens from the keyboard and moves with the arrows, skipping disabled and loading items", async () => {
    renderMenu();
    const user = await openWithKeyboard();
    expect(screen.getByRole("menu")).toBeInTheDocument();
    expect(focusedName()).toBe("Run workflow");
    await user.keyboard("{ArrowDown}");
    expect(focusedName()).toBe("View file history");
    await user.keyboard("{ArrowUp}");
    expect(focusedName()).toBe("Run workflow");
    await user.keyboard("{End}");
    expect(focusedName()).toBe("Clear history");
    await user.keyboard("{Home}");
    expect(focusedName()).toBe("Run workflow");
  });

  it.each([
    ["v", "View file history"],
    ["sh", "Share"],
    ["cl", "Clear history"],
  ])("jumps by type-ahead: %s", async (typed, expected) => {
    renderMenu();
    const user = await openWithKeyboard();
    await user.keyboard(typed);
    expect(focusedName()).toBe(expected);
  });

  it("opens a submenu with Right and closes it with Left", async () => {
    renderMenu();
    const user = await openWithKeyboard();
    await user.keyboard("sh");
    await user.keyboard("{ArrowRight}");
    expect(screen.getAllByRole("menu")).toHaveLength(2);
    expect(focusedName()).toBe("Copy link");
    await user.keyboard("{ArrowLeft}");
    expect(screen.getAllByRole("menu")).toHaveLength(1);
    expect(focusedName()).toBe("Share");
  });

  it("runs an item on Enter, closes and returns focus to the trigger", async () => {
    const onSelect = renderMenu();
    const user = await openWithKeyboard();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).toBeNull();
    expect(focused()).toBe(screen.getByRole("button", { name: "Actions" }));
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    renderMenu();
    const user = await openWithKeyboard();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(focused()).toBe(screen.getByRole("button", { name: "Actions" }));
  });

  it("opens on click", async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole("button", { name: "Actions" }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
  });

  it("names items by their label alone and describes them by their description", async () => {
    renderMenu();
    await openWithKeyboard();
    const menu = screen.getByRole("menu");
    expect(
      within(menu).getByRole("menuitem", { name: "Run workflow" }),
    ).toBeInTheDocument();
    const history = within(menu).getByRole("menuitem", {
      name: "View file history",
    });
    expect(history).toHaveAccessibleDescription(
      "Files picked up by earlier runs",
    );
  });

  it("styles destructive items apart", async () => {
    renderMenu();
    await openWithKeyboard();
    const item = screen.getByRole("menuitem", { name: "Clear history" });
    expect(item.dataset.destructive).toBe("true");
    expect(item.className).toContain("ui:text-destructive");
    const plain = screen.getByRole("menuitem", { name: "Run workflow" });
    expect(plain.dataset.destructive).toBeUndefined();
    expect(plain.className).not.toContain("ui:text-destructive");
  });

  it("marks a loading item busy and does not run it", async () => {
    const onSelect = renderMenu();
    const user = await openWithKeyboard();
    const item = screen.getByRole("menuitem", { name: "Export" });
    expect(item.getAttribute("aria-busy")).toBe("true");
    expect(item.getAttribute("aria-disabled")).toBe("true");
    await user.click(item);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("toggles checkbox items and picks radio items", async () => {
    const onChecked = vi.fn();
    const onValue = vi.fn();
    const user = userEvent.setup();
    render(
      <DropdownMenu defaultOpen>
        <DropdownMenuTrigger asChild>
          <MenuButton>View</MenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuCheckboxItem checked={false} onCheckedChange={onChecked}>
            Owned by
          </DropdownMenuCheckboxItem>
          <DropdownMenuRadioGroup value="name" onValueChange={onValue}>
            <DropdownMenuRadioItem value="name">Name</DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="created">
              Created date
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    const box = screen.getByRole("menuitemcheckbox", { name: "Owned by" });
    expect(box.getAttribute("aria-checked")).toBe("false");
    expect(
      screen
        .getByRole("menuitemradio", { name: "Name" })
        .getAttribute("aria-checked"),
    ).toBe("true");
    await user.click(box);
    expect(onChecked).toHaveBeenCalledWith(true);
  });

  it("picks a radio item", async () => {
    const onValue = vi.fn();
    const user = userEvent.setup();
    render(
      <DropdownMenu defaultOpen>
        <DropdownMenuTrigger asChild>
          <MenuButton>Sort</MenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuRadioGroup value="name" onValueChange={onValue}>
            <DropdownMenuRadioItem value="name">Name</DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="created">
              Created date
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    await user.click(
      screen.getByRole("menuitemradio", { name: "Created date" }),
    );
    expect(onValue).toHaveBeenCalledWith("created");
  });
});

describe("ContextMenu", () => {
  it("opens on right-click and runs an item", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <ContextMenu>
        <ContextMenuTrigger>Row</ContextMenuTrigger>
        <ContextMenuContent>
          <ContextMenuItem onSelect={onSelect}>Open</ContextMenuItem>
          <ContextMenuItem destructive>Delete</ContextMenuItem>
        </ContextMenuContent>
      </ContextMenu>,
    );
    expect(screen.queryByRole("menu")).toBeNull();
    fireEvent.contextMenu(screen.getByText("Row"), {
      clientX: 10,
      clientY: 10,
    });
    const menu = await screen.findByRole("menu");
    expect(
      within(menu).getByRole("menuitem", { name: "Delete" }).dataset
        .destructive,
    ).toBe("true");
    await user.click(within(menu).getByRole("menuitem", { name: "Open" }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).toBeNull();
  });
});

const action = (id: string, extra: Partial<MenuAction> = {}): MenuAction => ({
  id,
  label: id,
  onSelect: vi.fn(),
  ...extra,
});

describe("groupActions", () => {
  it("keeps first-seen group order and moves every destructive action into a last group", () => {
    const groups = groupActions([
      action("delete", { destructive: true }),
      action("edit"),
      action("open", { group: "links" }),
      action("copy"),
      action("archive", { destructive: true, group: "links" }),
    ]);
    expect(groups.map((group) => group.map((a) => a.id))).toEqual([
      ["edit", "copy"],
      ["open"],
      ["delete", "archive"],
    ]);
  });

  it("returns no groups for no actions", () => {
    expect(groupActions([])).toEqual([]);
  });
});

describe("RowActionMenu", () => {
  it("names the kebab, lists actions with destructive last after a separator, and runs one", async () => {
    const edit = action("Edit");
    const user = userEvent.setup();
    render(
      <RowActionMenu
        label="Actions for Invoice parser"
        actions={[
          action("Delete", { destructive: true }),
          edit,
          action("Share"),
        ]}
      />,
    );
    const kebab = screen.getByRole("button", {
      name: "Actions for Invoice parser",
    });
    await user.click(kebab);
    const menu = screen.getByRole("menu");
    const children = [...menu.querySelectorAll("[role]")].map((el) =>
      el.getAttribute("role") === "separator" ? "—" : el.textContent,
    );
    expect(children).toEqual(["Edit", "Share", "—", "Delete"]);
    await user.click(within(menu).getByRole("menuitem", { name: "Edit" }));
    expect(edit.onSelect).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("stays open when the action prevents the default, to show its loading state", async () => {
    const user = userEvent.setup();
    function Row() {
      const [loading, setLoading] = useState(false);
      return (
        <RowActionMenu
          label="Actions for Invoice parser"
          actions={[
            action("Export", {
              loading,
              onSelect: (event) => {
                event.preventDefault();
                setLoading(true);
              },
            }),
          ]}
        />
      );
    }
    render(<Row />);
    await user.click(screen.getByRole("button"));
    await user.click(screen.getByRole("menuitem", { name: "Export" }));
    const item = screen.getByRole("menuitem", { name: "Export" });
    expect(item.getAttribute("aria-busy")).toBe("true");
  });

  it("disables the kebab when there are no actions", () => {
    render(<RowActionMenu label="Actions for Archived" actions={[]} />);
    expect(
      screen.getByRole("button", { name: "Actions for Archived" }),
    ).toBeDisabled();
  });
});

describe("RowContextMenu", () => {
  it("opens the same actions on right-click of the row", async () => {
    const open = action("Open");
    const user = userEvent.setup();
    render(
      <RowContextMenu actions={[action("Delete", { destructive: true }), open]}>
        <div>Invoice parser</div>
      </RowContextMenu>,
    );
    fireEvent.contextMenu(screen.getByText("Invoice parser"));
    const menu = await screen.findByRole("menu");
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((item) => item.textContent),
    ).toEqual(["Open", "Delete"]);
    await user.click(within(menu).getByRole("menuitem", { name: "Open" }));
    expect(open.onSelect).toHaveBeenCalledTimes(1);
  });
});

describe("menu triggers", () => {
  it("are plain buttons that never submit a form", () => {
    render(
      <>
        <MenuButton>Sort by</MenuButton>
        <MenuIconButton aria-label="More" />
      </>,
    );
    expect(
      screen.getByRole("button", { name: "Sort by" }).getAttribute("type"),
    ).toBe("button");
    expect(
      screen.getByRole("button", { name: "More" }).getAttribute("type"),
    ).toBe("button");
  });
});
