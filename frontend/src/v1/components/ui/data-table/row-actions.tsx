import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  groupActions,
  MenuIconButton,
} from "@v1/components/ui/menu";
import { Fragment, type JSX } from "react";
import type { DataTableRowAction } from "./types";

/*
 * A row's kebab and its action menu, from P1-T09's menu parts. It is
 * `RowActionMenu` with one addition, `tabIndex` on the kebab, which the
 * table's roving focus needs to take other rows' kebabs out of the tab order.
 * Order and grouping are `groupActions`': destructive actions last, after a
 * separator.
 */

export type RowActionsProps = Readonly<{
  /** Names the row: "Actions for invoice-parser". */
  label: string;
  actions: readonly DataTableRowAction[];
  tabIndex?: number;
}>;

export function RowActions({
  label,
  actions,
  tabIndex,
}: RowActionsProps): JSX.Element {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <MenuIconButton
          aria-label={label}
          tabIndex={tabIndex}
          disabled={actions.length === 0}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {groupActions(actions).map((group, index) => (
          <Fragment key={group[0].id}>
            {index > 0 && <DropdownMenuSeparator />}
            {group.map(({ id, label: text, group: _group, ...item }) => (
              <DropdownMenuItem key={id} {...item}>
                {text}
              </DropdownMenuItem>
            ))}
          </Fragment>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
