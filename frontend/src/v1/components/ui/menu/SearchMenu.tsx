import { cn } from "@v1/lib/cn";
import { getPortalContainer } from "@v1/lib/portal";
import { Popover as RadixPopover } from "radix-ui";
import { type JSX, type ReactElement, useState } from "react";
import { MENU_SURFACE } from "./item";
import { Command, type CommandItem, type CommandProps } from "./Command";

/*
 * A menu with a search box at the top: a popover holding a Command. Use it
 * when a menu is long enough that people look for an entry by name (adding a
 * filter, moving to a folder, picking a column). For choosing a form value,
 * use the selection inputs (P1-T04) instead.
 */

export type SearchMenuProps = Omit<CommandProps, "autoFocus" | "className"> &
  Readonly<{
    /**
     * The control that opens the menu, used as the trigger itself
     * (`asChild`), so it must accept a ref and props: for now `MenuButton`
     * or `MenuIconButton`, the v1 `Button` once P1-T02 lands.
     */
    trigger: ReactElement;
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
    /** Default true. Set false for multi-select menus that stay open. */
    closeOnSelect?: boolean;
    align?: "start" | "center" | "end";
    side?: "top" | "right" | "bottom" | "left";
    /** Classes for the popover surface. */
    className?: string;
  }>;

/** A popover menu that filters its rows as you type. Escape closes it. */
export function SearchMenu({
  trigger,
  open: controlledOpen,
  onOpenChange,
  closeOnSelect = true,
  align = "start",
  side = "bottom",
  className,
  onSelect,
  onQueryChange,
  query,
  ...command
}: SearchMenuProps): JSX.Element {
  const [ownOpen, setOwnOpen] = useState(false);
  const [ownQuery, setOwnQuery] = useState("");
  const open = controlledOpen ?? ownOpen;
  const setOpen = (next: boolean) => {
    if (controlledOpen === undefined) {
      setOwnOpen(next);
    }
    // A menu reopens on a fresh search.
    if (!next && query === undefined) {
      setOwnQuery("");
    }
    onOpenChange?.(next);
  };
  const select = (item: CommandItem) => {
    onSelect?.(item);
    if (closeOnSelect) {
      setOpen(false);
    }
  };
  return (
    <RadixPopover.Root open={open} onOpenChange={setOpen}>
      <RadixPopover.Trigger asChild>{trigger}</RadixPopover.Trigger>
      <RadixPopover.Portal container={getPortalContainer()}>
        <RadixPopover.Content
          data-slot="search-menu-content"
          aria-label={command.label}
          align={align}
          side={side}
          sideOffset={4}
          collisionPadding={8}
          className={cn(
            MENU_SURFACE,
            "ui:flex ui:w-72 ui:max-h-(--radix-popover-content-available-height) ui:flex-col ui:overflow-hidden ui:p-0",
            className,
          )}
        >
          <Command
            {...command}
            query={query ?? ownQuery}
            onQueryChange={(next) => {
              if (query === undefined) {
                setOwnQuery(next);
              }
              onQueryChange?.(next);
            }}
            onSelect={select}
            listClassName="ui:max-h-80"
          />
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}
