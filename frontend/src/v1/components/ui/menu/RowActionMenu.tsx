import { Fragment, type JSX, type ReactElement } from "react";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "./ContextMenu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./DropdownMenu";
import type { MenuItemOptions } from "./item";
import { MenuIconButton } from "./MenuTrigger";

/*
 * The one action menu per table row (frames 621:1114, 1084:630): a kebab
 * that opens a list of actions. The same list can open on right-click with
 * RowContextMenu, so a data table passes one `actions` array to both.
 */

/** One action. Actions sharing a `group` sit together, between separators. */
export type MenuAction = MenuItemOptions &
  Readonly<{
    id: string;
    label: string;
    /**
     * Runs on click or Enter. The menu then closes, unless the handler calls
     * `event.preventDefault()` (e.g. to show `loading` while it works).
     */
    onSelect: (event: Event) => void;
    disabled?: boolean;
    /** Actions with the same group are drawn together, in first-seen order. */
    group?: string;
  }>;

const DESTRUCTIVE_GROUP = "\u0000destructive";

/**
 * Splits actions into groups in first-seen order, with every destructive
 * action moved into one last group, so they are always last and set apart by
 * a separator whatever order the caller gives.
 */
export function groupActions(
  actions: readonly MenuAction[],
): readonly (readonly MenuAction[])[] {
  const groups = new Map<string, MenuAction[]>();
  for (const action of actions) {
    const key = action.destructive ? DESTRUCTIVE_GROUP : (action.group ?? "");
    const group = groups.get(key);
    if (group) {
      group.push(action);
    } else {
      groups.set(key, [action]);
    }
  }
  const destructive = groups.get(DESTRUCTIVE_GROUP);
  groups.delete(DESTRUCTIVE_GROUP);
  const ordered = [...groups.values()];
  return destructive ? [...ordered, destructive] : ordered;
}

type Kind = "dropdown" | "context";

const PARTS = {
  dropdown: { Item: DropdownMenuItem, Separator: DropdownMenuSeparator },
  context: { Item: ContextMenuItem, Separator: ContextMenuSeparator },
} as const;

function ActionList({
  actions,
  kind,
}: Readonly<{ actions: readonly MenuAction[]; kind: Kind }>): JSX.Element {
  const { Item, Separator } = PARTS[kind];
  return (
    <>
      {groupActions(actions).map((group, index) => (
        <Fragment key={group[0].id}>
          {index > 0 && <Separator />}
          {group.map(({ id, label, group: _group, ...item }) => (
            <Item key={id} {...item}>
              {label}
            </Item>
          ))}
        </Fragment>
      ))}
    </>
  );
}

export type RowActionMenuProps = Readonly<{
  /**
   * The kebab's accessible name. Name the row, so a screen reader can tell
   * the rows apart: "Actions for Invoice parser", not "Actions".
   */
  label: string;
  actions: readonly MenuAction[];
  /** Which edge of the kebab the menu lines up with. Default "end". */
  align?: "start" | "center" | "end";
  disabled?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}>;

/** A row's kebab and its action menu. */
export function RowActionMenu({
  label,
  actions,
  align = "end",
  disabled,
  open,
  onOpenChange,
  className,
}: RowActionMenuProps): JSX.Element {
  return (
    <DropdownMenu open={open} onOpenChange={onOpenChange}>
      <DropdownMenuTrigger asChild>
        <MenuIconButton
          aria-label={label}
          disabled={disabled || actions.length === 0}
          className={className}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align}>
        <ActionList actions={actions} kind="dropdown" />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export type RowContextMenuProps = Readonly<{
  actions: readonly MenuAction[];
  /** The element right-click opens the menu on, e.g. the table row. */
  children: ReactElement;
  onOpenChange?: (open: boolean) => void;
}>;

/**
 * Opens a row's actions on right-click, at the pointer. `children` is used
 * as the trigger itself (`asChild`), so it must accept a ref and props.
 * Keep the kebab too: right-click is a shortcut, not the only way in.
 */
export function RowContextMenu({
  actions,
  children,
  onOpenChange,
}: RowContextMenuProps): JSX.Element {
  return (
    <ContextMenu onOpenChange={onOpenChange}>
      <ContextMenuTrigger asChild disabled={actions.length === 0}>
        {children}
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ActionList actions={actions} kind="context" />
      </ContextMenuContent>
    </ContextMenu>
  );
}
