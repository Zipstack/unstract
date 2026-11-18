import { cn } from "@v1/lib/cn";
import { getPortalContainer } from "@v1/lib/portal";
import { DropdownMenu as RadixDropdownMenu } from "radix-ui";
import type { ComponentProps, JSX } from "react";
import { MENU_SURFACE } from "./item";
import { createMenuParts } from "./parts";

/*
 * A menu opened from a button: Enter, Space or ArrowDown on the trigger opens
 * it, the arrow keys move, typing jumps to the first item that starts with
 * the letters typed, Enter selects, Escape closes and returns focus to the
 * trigger. All of that is Radix's.
 */

export type DropdownMenuProps = ComponentProps<typeof RadixDropdownMenu.Root>;

export function DropdownMenu(props: DropdownMenuProps): JSX.Element {
  return <RadixDropdownMenu.Root {...props} />;
}

export type DropdownMenuTriggerProps = ComponentProps<
  typeof RadixDropdownMenu.Trigger
>;

/**
 * The control that opens the menu. Pass `asChild` with your own button (for
 * now `MenuButton` or `MenuIconButton`; the v1 `Button` once P1-T02 lands).
 */
export function DropdownMenuTrigger(
  props: DropdownMenuTriggerProps,
): JSX.Element {
  return (
    <RadixDropdownMenu.Trigger data-slot="dropdown-menu-trigger" {...props} />
  );
}

export type DropdownMenuContentProps = ComponentProps<
  typeof RadixDropdownMenu.Content
>;

/**
 * The list, portalled into the v1 portal container. It never opens
 * off-screen: it flips to the other side and shifts along it to stay 8px
 * inside the viewport, and scrolls when taller than the room left.
 */
export function DropdownMenuContent({
  className,
  sideOffset = 4,
  collisionPadding = 8,
  ...props
}: DropdownMenuContentProps): JSX.Element {
  return (
    <RadixDropdownMenu.Portal container={getPortalContainer()}>
      <RadixDropdownMenu.Content
        data-slot="dropdown-menu-content"
        sideOffset={sideOffset}
        collisionPadding={collisionPadding}
        className={cn(
          MENU_SURFACE,
          "ui:max-h-(--radix-dropdown-menu-content-available-height)",
          className,
        )}
        {...props}
      />
    </RadixDropdownMenu.Portal>
  );
}

const parts = createMenuParts(RadixDropdownMenu, "dropdown-menu");

export const DropdownMenuItem = parts.Item;
export const DropdownMenuCheckboxItem = parts.CheckboxItem;
export const DropdownMenuRadioGroup = parts.RadioGroup;
export const DropdownMenuRadioItem = parts.RadioItem;
export const DropdownMenuLabel = parts.Label;
export const DropdownMenuSeparator = parts.Separator;
export const DropdownMenuGroup = parts.Group;
export const DropdownMenuSub = parts.Sub;
export const DropdownMenuSubTrigger = parts.SubTrigger;
export const DropdownMenuSubContent = parts.SubContent;
