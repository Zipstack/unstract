import { cn } from "@v1/lib/cn";
import { getPortalContainer } from "@v1/lib/portal";
import { ContextMenu as RadixContextMenu } from "radix-ui";
import type { ComponentProps, JSX } from "react";
import { MENU_SURFACE } from "./item";
import { createMenuParts } from "./parts";

/*
 * A menu opened by right-click (or the keyboard's context-menu key, or
 * Shift+F10) on its trigger area, at the pointer. Its items are the same
 * parts as DropdownMenu's, so a row's kebab menu and its right-click menu can
 * share one list (see RowContextMenu).
 */

export type ContextMenuProps = ComponentProps<typeof RadixContextMenu.Root>;

export function ContextMenu(props: ContextMenuProps): JSX.Element {
  return <RadixContextMenu.Root {...props} />;
}

export type ContextMenuTriggerProps = ComponentProps<
  typeof RadixContextMenu.Trigger
>;

/** The area that opens the menu. Pass `asChild` to use the element itself. */
export function ContextMenuTrigger(
  props: ContextMenuTriggerProps,
): JSX.Element {
  return (
    <RadixContextMenu.Trigger data-slot="context-menu-trigger" {...props} />
  );
}

export type ContextMenuContentProps = ComponentProps<
  typeof RadixContextMenu.Content
>;

/** The list, at the pointer; it flips and shifts to stay on-screen. */
export function ContextMenuContent({
  className,
  collisionPadding = 8,
  ...props
}: ContextMenuContentProps): JSX.Element {
  return (
    <RadixContextMenu.Portal container={getPortalContainer()}>
      <RadixContextMenu.Content
        data-slot="context-menu-content"
        collisionPadding={collisionPadding}
        className={cn(
          MENU_SURFACE,
          "ui:max-h-(--radix-context-menu-content-available-height)",
          className,
        )}
        {...props}
      />
    </RadixContextMenu.Portal>
  );
}

const parts = createMenuParts(RadixContextMenu, "context-menu");

export const ContextMenuItem = parts.Item;
export const ContextMenuCheckboxItem = parts.CheckboxItem;
export const ContextMenuRadioGroup = parts.RadioGroup;
export const ContextMenuRadioItem = parts.RadioItem;
export const ContextMenuLabel = parts.Label;
export const ContextMenuSeparator = parts.Separator;
export const ContextMenuGroup = parts.Group;
export const ContextMenuSub = parts.Sub;
export const ContextMenuSubTrigger = parts.SubTrigger;
export const ContextMenuSubContent = parts.SubContent;
