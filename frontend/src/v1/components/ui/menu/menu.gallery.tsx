import { ACTION_ICONS } from "@v1/lib/icons";
import { Columns3, RotateCcwClock } from "lucide-react";
import type { ReactElement } from "react";
import type { CommandGroup, CommandItem } from "./Command";
import { CommandPalette } from "./CommandPalette";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuTrigger,
} from "./ContextMenu";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "./DropdownMenu";
import { MenuButton } from "./MenuTrigger";
import { type MenuAction, RowActionMenu } from "./RowActionMenu";
import { SearchMenu } from "./SearchMenu";

/*
 * Every variant and state of the menus, for the component gallery (P1-T01,
 * not merged yet: register these there, where each entry is shown in Light,
 * Dark and Unstract). Until then markup.test.tsx renders each one, snapshots
 * its markup (the open menu included, from the portal) and runs the
 * accessibility scan on it.
 */

export type GalleryEntry = Readonly<{ name: string; element: ReactElement }>;

const noop = (): void => undefined;

/** Frame 621:1114, the Prompt Studio project row, with one action of each state. */
export const PROJECT_ACTIONS: readonly MenuAction[] = [
  {
    id: "delete",
    label: "Delete",
    icon: ACTION_ICONS.delete,
    destructive: true,
    onSelect: noop,
  },
  {
    id: "edit",
    label: "Edit",
    icon: ACTION_ICONS.edit,
    shortcut: "E",
    onSelect: noop,
  },
  {
    id: "duplicate",
    label: "Duplicate",
    icon: ACTION_ICONS.copy,
    onSelect: noop,
  },
  {
    id: "share",
    label: "Share",
    icon: ACTION_ICONS.share,
    onSelect: noop,
    disabled: true,
  },
  {
    id: "export",
    label: "Export",
    icon: ACTION_ICONS.download,
    loading: true,
    onSelect: noop,
  },
  {
    id: "endpoint",
    label: "Open API endpoint",
    icon: ACTION_ICONS.openExternal,
    group: "links",
    onSelect: noop,
  },
];

export const PALETTE_GROUPS: readonly CommandGroup[] = [
  {
    id: "pages",
    heading: "Pages",
    items: [
      {
        id: "workflows",
        label: "Workflows",
        icon: ACTION_ICONS.run,
        keywords: ["pipelines"],
      },
      { id: "logs", label: "Logs", icon: RotateCcwClock, shortcut: "G L" },
    ],
  },
  {
    id: "actions",
    heading: "Actions",
    items: [
      {
        id: "new-project",
        label: "New project",
        icon: ACTION_ICONS.add,
        description: "Create a Prompt Studio project",
        shortcut: "N",
      },
      {
        id: "import",
        label: "Import project",
        icon: ACTION_ICONS.upload,
        disabled: true,
      },
      {
        id: "clear",
        label: "Clear processed file history",
        icon: ACTION_ICONS.delete,
        destructive: true,
      },
    ],
  },
];

export const COLUMN_ITEMS: readonly CommandItem[] = [
  { id: "name", label: "Name", checked: true },
  { id: "owner", label: "Owned by", checked: true },
  { id: "created", label: "Created", checked: false, keywords: ["date"] },
  { id: "modified", label: "Modified", checked: false, keywords: ["date"] },
];

function fullMenu(open: boolean): ReactElement {
  return (
    <DropdownMenu defaultOpen={open} modal={false}>
      <DropdownMenuTrigger asChild>
        <MenuButton>Actions</MenuButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Workflow</DropdownMenuLabel>
          <DropdownMenuItem icon={ACTION_ICONS.run} shortcut="⌘↵">
            Run workflow
          </DropdownMenuItem>
          <DropdownMenuItem
            icon={RotateCcwClock}
            description="Files picked up by earlier runs"
          >
            View file history
          </DropdownMenuItem>
          <DropdownMenuItem icon={ACTION_ICONS.deploy} disabled>
            Deploy
          </DropdownMenuItem>
          <DropdownMenuItem icon={ACTION_ICONS.download} loading>
            Export
          </DropdownMenuItem>
        </DropdownMenuGroup>
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
        <DropdownMenuItem icon={ACTION_ICONS.delete} destructive>
          Clear processed file history
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export const MENU_GALLERY: readonly GalleryEntry[] = [
  { name: "dropdown closed", element: fullMenu(false) },
  {
    name: "dropdown open: icons, hint, description, disabled, loading, submenu, destructive",
    element: fullMenu(true),
  },
  {
    name: "dropdown open: sort (radio) and columns (checkbox)",
    element: (
      <DropdownMenu defaultOpen modal={false}>
        <DropdownMenuTrigger asChild>
          <MenuButton>Sort by</MenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuGroup>
            <DropdownMenuLabel>Sort by</DropdownMenuLabel>
            <DropdownMenuRadioGroup value="created">
              <DropdownMenuRadioItem value="name">Name</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="created">
                Created date
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="modified">
                Modified
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuLabel>Columns</DropdownMenuLabel>
            <DropdownMenuCheckboxItem checked icon={Columns3}>
              Owned by
            </DropdownMenuCheckboxItem>
            <DropdownMenuCheckboxItem checked={false} icon={Columns3}>
              Prompts
            </DropdownMenuCheckboxItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    ),
  },
  {
    name: "row actions closed",
    element: (
      <RowActionMenu
        label="Actions for Invoice parser"
        actions={PROJECT_ACTIONS}
      />
    ),
  },
  {
    name: "row actions open: destructive moved last",
    element: (
      <RowActionMenu
        label="Actions for Invoice parser"
        actions={PROJECT_ACTIONS}
        open
        onOpenChange={noop}
      />
    ),
  },
  {
    name: "row actions with no actions (disabled)",
    element: <RowActionMenu label="Actions for Archived parser" actions={[]} />,
  },
  {
    name: "context menu trigger area",
    element: (
      <ContextMenu>
        <ContextMenuTrigger className="ui:flex ui:h-20 ui:items-center ui:justify-center ui:rounded-lg ui:border ui:border-dashed ui:border-border ui:text-body-small ui:text-muted-foreground">
          Right-click here
        </ContextMenuTrigger>
        <ContextMenuContent />
      </ContextMenu>
    ),
  },
  {
    name: "search menu open, multi-select with checks",
    element: (
      <SearchMenu
        open
        onOpenChange={noop}
        closeOnSelect={false}
        label="Search columns"
        placeholder="Search columns…"
        items={COLUMN_ITEMS}
        trigger={<MenuButton>Columns</MenuButton>}
      />
    ),
  },
  {
    name: "search menu open, no match",
    element: (
      <SearchMenu
        open
        onOpenChange={noop}
        label="Search columns"
        query="zzz"
        items={COLUMN_ITEMS}
        emptyText="No matching columns"
        trigger={<MenuButton>Columns</MenuButton>}
      />
    ),
  },
  {
    name: "command palette open",
    element: (
      <CommandPalette open onOpenChange={noop} groups={PALETTE_GROUPS} />
    ),
  },
  {
    name: "command palette loading",
    element: (
      <CommandPalette
        open
        onOpenChange={noop}
        groups={[]}
        filter={false}
        loading
        query="invoice"
      />
    ),
  },
];
