import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import { getPortalContainer } from "@v1/lib/portal";
import { DropdownMenu } from "radix-ui";
import { Fragment, type JSX } from "react";
import type { DataTableRowAction } from "./types";

/*
 * SEAM: the one place the table gets its row action menu. It stands in for
 * P1-T09's menus (`@v1/components/ui/menu`, #2486, not on main yet) with
 * plain Radix and the same look (32px ghost kebab, popover surface, 32px
 * rows, destructive actions last after a separator). When #2486 merges, this
 * file becomes `DropdownMenu` + `DropdownMenuTrigger asChild` around
 * `MenuIconButton` (which takes `tabIndex`), with `groupActions` and
 * `DropdownMenuItem`/`DropdownMenuSeparator` for the list. `RowActionMenu`
 * itself takes no `tabIndex`, which the table's roving focus needs.
 */

export type RowActionsProps = Readonly<{
  /** Names the row: "Actions for invoice-parser". */
  label: string;
  actions: readonly DataTableRowAction[];
  tabIndex?: number;
}>;

const ITEM =
  "ui:relative ui:flex ui:min-h-8 ui:w-full ui:cursor-pointer ui:items-center ui:gap-2.5 ui:rounded-md ui:px-2 ui:py-1.5 ui:text-left ui:font-sans ui:text-body-small ui:font-medium ui:text-foreground ui:outline-none ui:select-none ui:focus-visible:focus-ring ui:data-highlighted:bg-accent ui:data-disabled:cursor-not-allowed ui:data-disabled:opacity-50";

/** Destructive actions go last, as P1-T09's `groupActions` orders them. */
function groups(
  actions: readonly DataTableRowAction[],
): readonly (readonly DataTableRowAction[])[] {
  const safe = actions.filter((action) => !action.destructive);
  const destructive = actions.filter((action) => action.destructive);
  return [safe, destructive].filter((group) => group.length > 0);
}

const MoreIcon = ACTION_ICONS.more;

export function RowActions({
  label,
  actions,
  tabIndex,
}: RowActionsProps): JSX.Element {
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          aria-label={label}
          tabIndex={tabIndex}
          disabled={actions.length === 0}
          data-slot="menu-icon-button"
          className="ui:inline-flex ui:size-8 ui:cursor-pointer ui:items-center ui:justify-center ui:rounded-md ui:border-0 ui:bg-transparent ui:p-0 ui:text-muted-foreground ui:outline-none ui:focus-visible:focus-ring ui:disabled:cursor-not-allowed ui:disabled:opacity-50 ui:not-disabled:hover:bg-accent ui:not-disabled:hover:text-foreground ui:data-[state=open]:bg-accent ui:data-[state=open]:text-foreground"
        >
          <MoreIcon aria-hidden className="ui:size-4" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal container={getPortalContainer()}>
        <DropdownMenu.Content
          align="end"
          sideOffset={4}
          className="ui:z-50 ui:min-w-48 ui:overflow-x-hidden ui:overflow-y-auto ui:rounded-lg ui:border ui:border-solid ui:border-border ui:bg-popover ui:p-1.5 ui:text-popover-foreground ui:shadow-md ui:outline-none"
        >
          {groups(actions).map((group, index) => (
            <Fragment key={group[0].id}>
              {index > 0 && (
                <DropdownMenu.Separator className="ui:-mx-1.5 ui:my-1.5 ui:h-px ui:bg-border" />
              )}
              {group.map((action) => (
                <DropdownMenu.Item
                  key={action.id}
                  disabled={action.disabled}
                  onSelect={action.onSelect}
                  className={cn(
                    ITEM,
                    action.destructive &&
                      "ui:text-destructive ui:data-highlighted:bg-destructive/10",
                  )}
                >
                  {action.label}
                </DropdownMenu.Item>
              ))}
            </Fragment>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
