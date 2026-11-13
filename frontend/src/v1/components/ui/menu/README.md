# Menus

The one menu system in v1 (P1-T09, UN-4332): dropdowns, row actions,
right-click menus, menus with a search box and the command palette. Import
everything from `@v1/components/ui/menu`.

| Component | Use it for |
| --- | --- |
| `DropdownMenu` + parts | A menu opened from a button: actions, sort, column toggles |
| `RowActionMenu` | The one kebab per table row and its actions, from an `actions` array |
| `RowContextMenu` | The same `actions` on right-click of the row |
| `ContextMenu` + parts | Any other right-click menu |
| `SearchMenu` | A long menu people search by name (add a filter, pick columns) |
| `CommandPalette` | The ⌘K / Ctrl+K palette; P2-T10 global search builds on it |
| `Command` | The search box and list inside the last two, for a new surface |

To pick a form value, use the selection inputs (P1-T04) instead: a menu runs
actions, a select holds a value.

## Rows

Every row takes the same options (`MenuItemOptions`):

| Prop | Shows |
| --- | --- |
| `icon` | A 16px lucide glyph before the label (`ACTION_ICONS.edit`) |
| `shortcut` | A hint at the end ("⌘D"). Hidden from screen readers: bind the key yourself and pass `aria-keyshortcuts` |
| `description` | A second line, read as the row's description, not its name |
| `destructive` | The destructive colour. Destructive rows go last, after a separator |
| `loading` | A spinner instead of the icon; the row is disabled and `aria-busy` |

Rows are 32 tall (more with a description), radius 8, with a 13px medium
label (frames 621:1114, 1084:630, 780:3510). The surface is the popover
colour, radius 10, `shadow-md`, at least 192 wide.

## DropdownMenu

shadcn-style parts on Radix: `DropdownMenu`, `DropdownMenuTrigger`,
`DropdownMenuContent`, `DropdownMenuItem`, `DropdownMenuCheckboxItem`,
`DropdownMenuRadioGroup` / `DropdownMenuRadioItem`, `DropdownMenuGroup`,
`DropdownMenuLabel`, `DropdownMenuSeparator`, `DropdownMenuSub`,
`DropdownMenuSubTrigger` / `DropdownMenuSubContent`. `ContextMenu` has the same
parts with a `ContextMenu` prefix.

```tsx
<DropdownMenu>
  <DropdownMenuTrigger asChild>
    <MenuButton>Actions</MenuButton>
  </DropdownMenuTrigger>
  <DropdownMenuContent align="end">
    <DropdownMenuItem icon={ACTION_ICONS.run} onSelect={run}>Run workflow</DropdownMenuItem>
    <DropdownMenuSub>
      <DropdownMenuSubTrigger icon={ACTION_ICONS.share}>Share</DropdownMenuSubTrigger>
      <DropdownMenuSubContent>…</DropdownMenuSubContent>
    </DropdownMenuSub>
    <DropdownMenuSeparator />
    <DropdownMenuItem icon={ACTION_ICONS.delete} destructive onSelect={remove}>
      Delete
    </DropdownMenuItem>
  </DropdownMenuContent>
</DropdownMenu>
```

Keyboard (Radix): Enter, Space or ArrowDown on the trigger opens; the arrows,
Home and End move, skipping disabled rows; typing jumps to the first row that
starts with what was typed; Right opens a submenu and Left closes it; Enter
runs a row; Escape closes and returns focus to the trigger. The list never
opens off-screen: it flips to the other side, shifts to stay 8px inside the
viewport, and scrolls when taller than the room left.

`onSelect` closes the menu. Call `event.preventDefault()` in it to keep the
menu open, for example while the row shows `loading`.

## RowActionMenu and RowContextMenu

```tsx
const actions: MenuAction[] = [
  { id: "edit", label: "Edit", icon: ACTION_ICONS.edit, onSelect: edit },
  { id: "share", label: "Share", icon: ACTION_ICONS.share, onSelect: share },
  { id: "endpoint", label: "Open API endpoint", icon: ACTION_ICONS.openExternal, group: "links", onSelect: open },
  { id: "delete", label: "Delete", icon: ACTION_ICONS.delete, destructive: true, onSelect: remove },
];

<RowContextMenu actions={actions}>
  <tr>
    …
    <td><RowActionMenu label={`Actions for ${row.name}`} actions={actions} /></td>
  </tr>
</RowContextMenu>
```

- `label` names the kebab. Name the row ("Actions for Invoice parser"), so a
  screen reader can tell the kebabs apart.
- Actions with the same `group` sit together, in first-seen order, between
  separators. Every `destructive` action is moved into one last group,
  whatever order it was given in (`groupActions`).
- With no actions the kebab is disabled, and right-click does nothing.
- `RowContextMenu` uses its child as the trigger (`asChild`), so the child
  must accept a ref and props. Keep the kebab too: right-click is a
  shortcut, not the only way in.

## SearchMenu, CommandPalette and Command

All three take rows as data: `items` (one list) or `groups`
(`{ id, heading?, items }[]`), each row a `CommandItem`, which is
`MenuItemOptions` plus `id`, `label`, `keywords`, `disabled`, `checked` and
its own `onSelect`.

```tsx
<SearchMenu
  label="Search columns"
  items={columns.map((c) => ({ id: c.id, label: c.name, checked: c.visible }))}
  closeOnSelect={false}
  onSelect={(item) => toggleColumn(item.id)}
  trigger={<MenuButton>Columns</MenuButton>}
/>

const [open, setOpen] = useState(false);
useCommandPaletteShortcut(() => setOpen(true));
<CommandPalette open={open} onOpenChange={setOpen} groups={groups} />
```

- **Filtering.** By default rows whose label or `keywords` contain the query
  (ignoring case) stay, and empty groups are hidden. For a server search, pass
  `filter={false}` with `query` and `onQueryChange`, and give only the rows
  that matched; `loading` shows "Loading…" meanwhile.
- **Keyboard.** The ARIA combobox pattern: focus stays in the search box,
  which points at the active row with `aria-activedescendant`. Up and Down
  move, wrapping and skipping disabled and loading rows; Enter runs the active
  row; Escape closes. The pointer moves the active row too.
- **Status rows** ("No results", "Loading…") are an `<output>` beside the
  listbox, and the listbox is hidden meanwhile: an empty listbox fails the
  accessibility scan.
- `checked` gives a row a check and `aria-checked`; any checked value in a
  group gives the whole group a check column, so labels line up.
- `SearchMenu` closes on a select unless `closeOnSelect={false}`, and starts
  each opening with an empty query unless the query is controlled.
- `CommandPalette` sits near the top of the screen over the scrim, with key
  hints in the footer (`footer` replaces them). Mount
  `useCommandPaletteShortcut` once, in the shell.

## Triggers: a temporary seam

`MenuButton` (outline, label and chevron) and `MenuIconButton` (32px ghost
icon button, the kebab by default) stand in for the v1 `Button`, which
P1-T02 (UN-4272) has not built yet. When it lands they become thin wrappers
over it and callers do not change. Until then, pass one of them (or any
element that accepts a ref and props) to `DropdownMenuTrigger asChild` or
`SearchMenu trigger`.

## Tests

`menu.test.tsx` and `command.test.tsx` cover behaviour and keyboard use.
`markup.test.tsx` snapshots every gallery entry (open menus included, from
the portal) into `__snapshots__/markup.md` and runs the accessibility scan on
each. The gallery entries are in `menu.gallery.tsx`, ready for P1-T01.
