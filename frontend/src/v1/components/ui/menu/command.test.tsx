import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import {
  Command,
  type CommandGroup,
  type CommandItem,
  filterGroups,
  matchesQuery,
  nextEnabled,
} from "./Command";
import { CommandPalette, useCommandPaletteShortcut } from "./CommandPalette";
import { MenuButton } from "./MenuTrigger";
import { SearchMenu } from "./SearchMenu";

const GROUPS: readonly CommandGroup[] = [
  {
    id: "pages",
    heading: "Pages",
    items: [
      { id: "workflows", label: "Workflows", keywords: ["pipelines"] },
      { id: "logs", label: "Logs", disabled: true },
    ],
  },
  {
    id: "actions",
    heading: "Actions",
    items: [
      {
        id: "new",
        label: "New project",
        description: "Create a Prompt Studio project",
      },
      { id: "export", label: "Export", loading: true },
      { id: "clear", label: "Clear history", destructive: true },
    ],
  },
];

const input = () => screen.getByRole("combobox");
const activeLabel = () => {
  const id = input().getAttribute("aria-activedescendant");
  return id
    ? document.getElementById(id)?.querySelector(".ui\\:truncate")?.textContent
    : undefined;
};

describe("matchesQuery, filterGroups and nextEnabled", () => {
  const item: CommandItem = { id: "a", label: "Workflows", keywords: ["ETL"] };

  it("matches a case-insensitive substring of the label or a keyword", () => {
    expect(matchesQuery(item, "FLOW")).toBe(true);
    expect(matchesQuery(item, "etl")).toBe(true);
    expect(matchesQuery(item, "  ")).toBe(true);
    expect(matchesQuery(item, "logs")).toBe(false);
  });

  it("drops groups left empty, and only empty groups when not filtering", () => {
    expect(filterGroups(GROUPS, "pipe", true).map((g) => g.id)).toEqual([
      "pages",
    ]);
    const withEmpty = [...GROUPS, { id: "none", items: [] }];
    expect(filterGroups(withEmpty, "zzz", false).map((g) => g.id)).toEqual([
      "pages",
      "actions",
    ]);
  });

  it("wraps and skips disabled and loading rows", () => {
    const rows = GROUPS.flatMap((g) => g.items);
    expect(nextEnabled(rows, 0, 1)).toBe(2);
    expect(nextEnabled(rows, 2, 1)).toBe(4);
    expect(nextEnabled(rows, 4, 1)).toBe(0);
    expect(nextEnabled(rows, 0, -1)).toBe(4);
    expect(nextEnabled([{ id: "x", label: "x", disabled: true }], -1, 1)).toBe(
      -1,
    );
  });
});

describe("Command", () => {
  it("is a combobox over a listbox of grouped options", () => {
    render(<Command label="Search commands" groups={GROUPS} />);
    expect(input()).toHaveFocus();
    expect(input().getAttribute("aria-controls")).toBe(
      screen.getByRole("listbox", { name: "Search commands" }).id,
    );
    expect(screen.getByRole("group", { name: "Pages" })).toBeInTheDocument();
    expect(activeLabel()).toBe("Workflows");
    const option = screen.getByRole("option", { name: "New project" });
    expect(option).toHaveAccessibleDescription(
      "Create a Prompt Studio project",
    );
    expect(
      screen
        .getByRole("option", { name: "Logs" })
        .getAttribute("aria-disabled"),
    ).toBe("true");
    expect(
      screen.getByRole("option", { name: "Clear history" }).dataset.destructive,
    ).toBe("true");
  });

  it("moves with the arrows, wrapping and skipping unavailable rows, and runs the active row on Enter", async () => {
    const onSelect = vi.fn();
    const onItem = vi.fn();
    const user = userEvent.setup();
    const groups: readonly CommandGroup[] = [
      GROUPS[0],
      {
        ...GROUPS[1],
        items: GROUPS[1].items.map((item) =>
          item.id === "clear" ? { ...item, onSelect: onItem } : item,
        ),
      },
    ];
    render(<Command label="Search" groups={groups} onSelect={onSelect} />);
    await user.keyboard("{ArrowDown}");
    expect(activeLabel()).toBe("New project");
    await user.keyboard("{ArrowDown}");
    expect(activeLabel()).toBe("Clear history");
    await user.keyboard("{ArrowDown}");
    expect(activeLabel()).toBe("Workflows");
    await user.keyboard("{ArrowUp}");
    expect(activeLabel()).toBe("Clear history");
    await user.keyboard("{Enter}");
    expect(onItem).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: "clear" }),
    );
  });

  it("filters as you type, matching keywords, and resets the active row", async () => {
    const user = userEvent.setup();
    render(<Command label="Search" groups={GROUPS} />);
    await user.keyboard("{ArrowDown}");
    await user.keyboard("pipe");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Workflows",
    ]);
    expect(screen.queryByRole("group", { name: "Actions" })).toBeNull();
    expect(activeLabel()).toBe("Workflows");
  });

  it("says so when nothing matches, without an empty listbox", async () => {
    const user = userEvent.setup();
    render(
      <Command label="Search" groups={GROUPS} emptyText="No matching pages" />,
    );
    await user.keyboard("zzz");
    expect(screen.getByRole("status").textContent).toBe("No matching pages");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(input().getAttribute("aria-activedescendant")).toBeNull();
    await user.keyboard("{Enter}");
  });

  it("shows the loading state instead of rows", () => {
    render(<Command label="Search" groups={GROUPS} loading />);
    expect(screen.getByRole("status").textContent).toBe("Loading…");
    expect(screen.queryByRole("option")).toBeNull();
    expect(input().getAttribute("aria-activedescendant")).toBeNull();
  });

  it("leaves filtering to the caller with filter={false} and a controlled query", async () => {
    const user = userEvent.setup();
    const onQueryChange = vi.fn();
    function Search() {
      const [query, setQuery] = useState("");
      return (
        <Command
          label="Search"
          filter={false}
          query={query}
          onQueryChange={(next) => {
            onQueryChange(next);
            setQuery(next);
          }}
          items={[{ id: "server", label: "Server result" }]}
        />
      );
    }
    render(<Search />);
    await user.keyboard("zz");
    expect(onQueryChange).toHaveBeenLastCalledWith("zz");
    expect(input()).toHaveValue("zz");
    expect(screen.getByRole("option", { name: "Server result" })).toBeVisible();
  });

  it("follows the pointer and runs a clicked row, but not an unavailable one", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<Command label="Search" groups={GROUPS} onSelect={onSelect} />);
    fireEvent.mouseMove(screen.getByRole("option", { name: "New project" }));
    expect(activeLabel()).toBe("New project");
    fireEvent.mouseMove(screen.getByRole("option", { name: "Logs" }));
    expect(activeLabel()).toBe("New project");
    await user.click(screen.getByRole("option", { name: "Logs" }));
    expect(onSelect).not.toHaveBeenCalled();
    await user.click(screen.getByRole("option", { name: "Workflows" }));
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: "workflows" }),
    );
    expect(input()).toHaveFocus();
  });

  it("marks checked rows, and gives the whole group a check column", () => {
    render(
      <Command
        label="Columns"
        items={[
          { id: "a", label: "Name", checked: true },
          { id: "b", label: "Owner", checked: false },
        ]}
      />,
    );
    expect(
      screen.getByRole("option", { name: "Name" }).getAttribute("aria-checked"),
    ).toBe("true");
    expect(
      screen
        .getByRole("option", { name: "Owner" })
        .getAttribute("aria-checked"),
    ).toBe("false");
  });

  it("gives rows valid DOM ids even when their ids hold spaces", async () => {
    const user = userEvent.setup();
    render(
      <Command
        label="Search"
        items={[
          { id: "first row", label: "First" },
          { id: "second row", label: "Second" },
        ]}
      />,
    );
    await user.keyboard("{ArrowDown}");
    const ref = input().getAttribute("aria-activedescendant") ?? "";
    expect(ref).not.toMatch(/\s/);
    expect(document.getElementById(ref)?.textContent).toBe("Second");
  });

  it("reports the list collapsed while a status row replaces it", async () => {
    const user = userEvent.setup();
    render(<Command label="Search" groups={GROUPS} />);
    expect(input().getAttribute("aria-expanded")).toBe("true");
    await user.keyboard("zzz");
    expect(input().getAttribute("aria-expanded")).toBe("false");
    expect(input().getAttribute("aria-controls")).toBeNull();
  });

  it("keeps the status region mounted, so a change to no results is announced", async () => {
    const user = userEvent.setup();
    render(<Command label="Search" groups={GROUPS} />);
    const region = screen.getByRole("status");
    expect(region.textContent).toBe("");
    await user.keyboard("zzz");
    expect(screen.getByRole("status")).toBe(region);
    expect(region.textContent).toBe("No results");
  });

  it("names a group whose id holds spaces", () => {
    render(
      <Command
        label="Search"
        groups={[
          {
            id: "recent files",
            heading: "Recent files",
            items: [{ id: "a", label: "a.pdf" }],
          },
        ]}
      />,
    );
    expect(
      screen.getByRole("group", { name: "Recent files" }),
    ).toBeInTheDocument();
  });

  it("ignores Enter while composing text (IME)", () => {
    const onSelect = vi.fn();
    render(<Command label="Search" groups={GROUPS} onSelect={onSelect} />);
    fireEvent.keyDown(input(), { key: "Enter", isComposing: true });
    expect(onSelect).not.toHaveBeenCalled();
  });
});

describe("SearchMenu", () => {
  function renderSearchMenu(
    props: Partial<Parameters<typeof SearchMenu>[0]> = {},
  ) {
    const onSelect = vi.fn();
    render(
      <SearchMenu
        label="Search columns"
        items={[
          { id: "name", label: "Name" },
          { id: "owner", label: "Owned by" },
        ]}
        onSelect={onSelect}
        trigger={<MenuButton>Columns</MenuButton>}
        {...props}
      />,
    );
    return onSelect;
  }

  it("opens from its trigger with the search box focused, filters, and closes on Enter", async () => {
    const user = userEvent.setup();
    const onSelect = renderSearchMenu();
    const trigger = screen.getByRole("button", { name: "Columns" });
    await user.click(trigger);
    expect(
      screen.getByRole("dialog", { name: "Search columns" }),
    ).toBeVisible();
    expect(input()).toHaveFocus();
    await user.keyboard("own{Enter}");
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: "owner" }),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it("stays open with closeOnSelect={false}", async () => {
    const user = userEvent.setup();
    const onSelect = renderSearchMenu({ closeOnSelect: false });
    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("dialog")).toBeVisible();
  });

  it("opens on a fresh search when the caller closed it", async () => {
    const user = userEvent.setup();
    function Controlled() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(false)}>
            Apply
          </button>
          <SearchMenu
            open={open}
            onOpenChange={setOpen}
            label="Search columns"
            items={[
              { id: "name", label: "Name" },
              { id: "owner", label: "Owned by" },
            ]}
            trigger={<MenuButton>Columns</MenuButton>}
          />
        </>
      );
    }
    render(<Controlled />);
    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.keyboard("own");
    expect(screen.getAllByRole("option")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Columns" }));
    expect(input()).toHaveValue("");
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });

  it("adds the caller's list classes to its own", async () => {
    const user = userEvent.setup();
    renderSearchMenu({ listClassName: "ui:max-h-120" });
    await user.click(screen.getByRole("button", { name: "Columns" }));
    expect(screen.getByRole("listbox").className).toContain("ui:max-h-120");
  });

  it("closes on Escape and opens again on a fresh search", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    renderSearchMenu({ onOpenChange });
    const trigger = screen.getByRole("button", { name: "Columns" });
    await user.click(trigger);
    await user.keyboard("own");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
    expect(trigger).toHaveFocus();
    await user.click(trigger);
    expect(input()).toHaveValue("");
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });
});

describe("CommandPalette", () => {
  it("is a named dialog that runs a command and asks to close", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const onSelect = vi.fn();
    render(
      <CommandPalette
        open
        onOpenChange={onOpenChange}
        groups={GROUPS}
        onSelect={onSelect}
      />,
    );
    const dialog = screen.getByRole("dialog", { name: "Command palette" });
    expect(
      within(dialog).getByRole("combobox", { name: "Search commands" }),
    ).toHaveFocus();
    expect(within(dialog).getByText("to select")).toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: "workflows" }),
    );
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("asks to close on Escape, and keeps open after a select when told", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(
      <CommandPalette
        open
        onOpenChange={onOpenChange}
        groups={GROUPS}
        closeOnSelect={false}
        footer={<div>Custom footer</div>}
      />,
    );
    expect(screen.getByText("Custom footer")).toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect(onOpenChange).not.toHaveBeenCalled();
    await user.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

describe("useCommandPaletteShortcut", () => {
  function Shortcut({ onOpen }: Readonly<{ onOpen: () => void }>) {
    useCommandPaletteShortcut(onOpen);
    return null;
  }

  it("leaves handled, composing and key-less events alone, and takes an upper-case key", () => {
    const onOpen = vi.fn();
    function Upper() {
      useCommandPaletteShortcut(onOpen, "K");
      return null;
    }
    render(<Upper />);
    const handled = new KeyboardEvent("keydown", {
      key: "k",
      ctrlKey: true,
      cancelable: true,
    });
    handled.preventDefault();
    document.dispatchEvent(handled);
    fireEvent.keyDown(document, { key: "k", ctrlKey: true, isComposing: true });
    document.dispatchEvent(new KeyboardEvent("keydown", { ctrlKey: true }));
    expect(onOpen).not.toHaveBeenCalled();
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("fires on Ctrl+K and ⌘K only, and stops listening on unmount", () => {
    const onOpen = vi.fn();
    const { unmount } = render(<Shortcut onOpen={onOpen} />);
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    fireEvent.keyDown(document, { key: "K", metaKey: true });
    fireEvent.keyDown(document, { key: "k" });
    fireEvent.keyDown(document, { key: "k", ctrlKey: true, shiftKey: true });
    fireEvent.keyDown(document, { key: "j", ctrlKey: true });
    expect(onOpen).toHaveBeenCalledTimes(2);
    unmount();
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    expect(onOpen).toHaveBeenCalledTimes(2);
  });
});
