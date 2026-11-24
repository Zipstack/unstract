# Data table

The one table for every list in v1 (P1-T11, UN-4346), on TanStack Table.
Resource list pages (P2-T04), the logs console (P2-T07) and API Hub
administration (P9-T10) build on it, so the props below are a contract: add
to them, do not rename them.

```tsx
import { DataTable, type DataTableColumn } from "@v1/components/ui/data-table";

const columns: DataTableColumn<Deployment>[] = [
  { id: "name", header: "Name", sortKey: "name", width: "xl", cell: (d) => d.name },
  { id: "workflow", header: "Workflow", priority: 3, cell: (d) => d.workflow },
  { id: "runs", header: "Total runs", sortKey: "runs", align: "end", priority: 4, cell: (d) => d.runs },
];

<DataTable
  label="API deployments"
  columns={columns}
  rows={deployments}
  getRowId={(d) => d.id}
  getRowLabel={(d) => d.name}
  pagination={{ mode: "server", page, pageSize, total, onPageChange: setPage }}
  onSortChange={setSort}
  selectable
  bulkActions={({ selectedIds, clearSelection }) => <Button …>Delete selected</Button>}
  onRowClick={(d) => openDrawer(d.id)}
  rowActions={(d) => [{ id: "edit", label: "Edit", onSelect: () => edit(d) }]}
  getRowTone={(d) => (d.lastRunFailed ? "failure" : "default")}
  loading={query.isPending}
  error={query.isError ? { title: "Could not load deployments", onRetry: query.refetch } : null}
  filtered={search !== ""}
  toolbar={<Toolbar />}
  empty={<EmptyState … />}
  noResults={<NoResults … />}
/>
```

## Columns

| Field | Type | |
| --- | --- | --- |
| `id` | `string` | unique; `DataTableSort.columnId` names it |
| `header` | `string` | header text and the column's accessible name, drawn in overline caps |
| `cell` | `(row, { tabIndex, active }) => ReactNode` | put `tabIndex` on any link or button in the cell, so it leaves the tab order with its row |
| `sortKey` | `keyof TRow` or `(row) => string \| number \| boolean \| Date \| null` | makes the column sortable; see Sorting |
| `priority` | `1 \| 2 \| 3 \| 4` | default 1; see Column priority |
| `align` | `"start" \| "center" \| "end"` | default `start`; numbers go `end` |
| `width` | `"xs" \| "sm" \| "md" \| "lg" \| "xl"` | 48, 96, 160, 224, 320 (space tokens); columns without one share the rest |

## Props

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `label` | `string` | required | names the table ("API deployments"), its loading status, its bulk bar ("Bulk actions for API deployments") and its pagination ("API deployments pages"); unique on the page, or two landmarks share a name |
| `columns` | `DataTableColumn<TRow>[]` | required | memoise it: a new array rebuilds the column model |
| `rows` | `TRow[]` | required | |
| `getRowId` | `(row) => string` | required | selection and expansion are keyed by it |
| `getRowLabel` | `(row) => string` | required | read in the row controls' names: "Select invoice-parser", "Actions for invoice-parser", "Details for invoice-parser" |
| `sort` / `defaultSort` / `onSortChange` | `DataTableSort \| null` | `null` | controlled with `sort` (`null` is no sort), else the table holds it; server-paged headers sort only with `onSortChange` |
| `pagination` | `DataTablePagination` | none | `{ mode: "client", defaultPageSize?, resetKey? }` or `{ mode: "server", page, pageSize, total, onPageChange, onPageSizeChange? }`; both take `pageSizeOptions` |
| `selectable` | `boolean` | `false` | the checkbox column and the bulk bar |
| `selectedIds` / `defaultSelectedIds` / `onSelectionChange` | `string[]` | `[]` | controlled with `selectedIds`, else the table holds it; see Selection for filtered rows |
| `bulkActions` | `({ selectedIds, selectedRows, clearSelection }) => ReactNode` | | the bulk bar's actions |
| `renderExpanded` | `(row) => ReactNode` | | detail shown in place under the row; adds the expand column |
| `canExpand` | `(row) => boolean` | every row | |
| `defaultExpandedIds` | `string[]` | `[]` | |
| `onRowClick` | `(row) => void` | | the row click target: a click anywhere on the row, or Enter on it |
| `rowActions` | `(row) => DataTableRowAction[]` | | the kebab at the row's end; P1-T09's `MenuAction`: `{ id, label, onSelect, disabled?, destructive?, icon?, … }` |
| `getRowTone` | `(row) => "default" \| "failure"` | `default` | the failure tint |
| `loading` | `boolean` | `false` | skeleton rows instead of the body |
| `loadingRows` | `number` | the page size with pagination, else 5 | at most 10 either way |
| `error` | `{ title, message?, onRetry? } \| null` | | an inline error above the table; loaded rows stay |
| `filtered` | `boolean` | `false` | a search or filter is narrowing the rows, so no rows means no results |
| `toolbar`, `empty`, `noResults`, `footer` | `ReactNode` | | the slots |
| `scroll` | `"page" \| "container"` | `page` | see Scrolling |
| `className` | `string` | | on the root; give a `container` table its height here |

## Behaviour

- **Rows** are 56 tall (the spec; frames draw 52). The header is 40, muted,
  sticky. A selected row is `primary-muted` with a 2px `primary` bar on its
  left edge; a hovered row `accent`; a failed row (`getRowTone`) the
  `destructive` token at 5%, and 10% on hover. The tint is colour only, so
  say "failed" in a cell too.
- **Sorting** is single-column. A sortable header is a button: click, Enter or
  Space cycles ascending, descending, off. The sorted header carries
  `aria-sort`. Client sorting compares the `sortKey` values: numbers and
  dates by value, text case-blind and numeric-aware ("run 2" before
  "run 10"), and missing values (`null`, `undefined`) last in both
  directions; `NaN` and an invalid date count as missing. A string `sortKey`
  must name a field holding one of those types (checked by TypeScript).
  With `pagination.mode: "server"` the table does not reorder rows: it
  reports the sort through `onSortChange` (headers sort only when it is
  given) and the page refetches. A new sort goes back to page 1 in both
  modes (server: `onPageChange(1)`), and a `container` table scrolls back
  to the top on a new sort or page.
- **Pagination** uses `Pagination` from `navigation`. `client` pages the
  rows given; `server` shows the rows given as page `page` of `total`.
  Without `pagination` every row renders. A client page past the end (the
  rows shrank) shows the last page, and stays there; a refetch that empties
  the rows meanwhile comes back on the same page. A client table goes back
  to page 1 when the sort changes, when `filtered` flips and when
  `pagination.resetKey` changes: pass the search text there. Client
  `defaultPageSize` is the starting size (the user can change it); a size
  that is not a whole number above 0 falls back to 25. The sizes offered
  default to 10, 25, 50 and 100.
- **Selection** is keyed by row id. With server pagination it survives page
  changes, and the count includes rows on other pages. Otherwise the count,
  the header box, the announcements and the bulk bar's `selectedIds` and
  `selectedRows` cover only the rows in `rows`, so a bulk action never
  touches a row the user cannot see. While `filtered`, a selected row the
  filter hides stays selected through other changes (`onSelectionChange`
  reports it) and shows as selected when the filter clears. Unfiltered, a
  row missing from `rows` counts as gone: the next change drops its id.
  "Clear selection" clears everything, hidden rows included. The header box
  selects or clears the rows on the current page; it shows mixed
  (`aria-checked="mixed"`) when some are selected. The bulk bar (count,
  "Clear selection", then `bulkActions`) sits between the toolbar and the
  table while anything is selected; with server pagination `selectedRows`
  holds only the rows loaded now, so act on `selectedIds`.
- **Expansion** opens a detail row under the row; the toggle has
  `aria-expanded` and `aria-controls`.
- **Column priority**: a column shows when the screen is at least as wide as
  its priority needs, at the dev spec's breakpoints (board 683:135,
  section 7): priority 1 always, 2 from 1024, 3 from 1280, 4 from 1440. List
  screens stay usable to 768, where only priority 1 is left. Media queries,
  so a column drops only when a breakpoint is crossed. Pages set priorities;
  the table owns the breakpoints. A sort on a dropped column stays.
- **States**: loading (skeleton rows and a "Loading …" status), empty
  (`empty`), no results (`noResults`, while `filtered`), partial selection,
  all selected, error (`error`, an `InlineAlert` with Retry above the table;
  with no rows, nothing under it).

## Keyboard and screen readers

- Tab reaches the header boxes and sort buttons, then one row (roving
  focus), then that row's own controls. Up and Down move between rows, Home
  and End go to the first and last. Controls in other rows are out of the tab
  order, so a long page is not a long Tab.
- On a focused row: Enter runs `onRowClick` (or toggles the detail when there
  is none), Space toggles its selection, Right and Left open and close its
  detail.
- The bulk bar is before the table: Shift+Tab from a row goes back through
  the sort buttons and the header box to it.
- If the focused control goes away (Clear selection, Retry, a row deleted
  from its own menu, the skeleton replacing the body), focus moves to the
  active row, or to the header when there are no rows, rather than
  dropping to the page. Once the user has moved out of the table, it is
  left alone.
- One polite status region announces what the user did, once it shows:
  "Sorted by Name, ascending", "Sort cleared", "3 rows selected", "All 25
  rows on this page selected, 40 in total", "Selection cleared". A
  controlled parent that ignores a change announces nothing.
- `rowActions` open from the kebab and on right-click anywhere on the row
  (`RowContextMenu`); the kebab stays, so right-click is only a shortcut.
- A cell renderer gets `{ tabIndex, active }`: `tabIndex` is -1 in every
  row but the active one. Put it on any link or button the cell renders, or
  that control stays a tab stop in every row.
- Clicks on a link, button, input, checkbox, switch, radio, slider or menu
  item inside a row belong to that control, not to `onRowClick`; so does
  anything inside an element with `data-row-click="ignore"`. Keep
  interactive content in cells rare: use the row click target and
  `rowActions`.

## Scrolling

- `page` (default): the frame clips but does not scroll, so the header
  sticks to whatever scrolls the page (the content region). Columns drop by
  priority instead of scrolling sideways.
- `container`: the table scrolls inside its own frame. Give the root a height
  (`className="ui:h-160"`, or fill a flex parent). Past 50 rows only the rows in view render (TanStack Virtual), with
  `aria-rowcount` and `aria-rowindex` so screen readers still hear the full
  count (open detail rows included). Rows are measured, so expanded rows
  keep their height. The active row always renders, so Tab still reaches the
  body after the user scrolls away from it.

## Built from

- `Checkbox` from `@v1/components/ui/toggles` (P1-T05) for the row and header
  boxes.
- `RowActionMenu` and `RowContextMenu` from `@v1/components/ui/menu`
  (P1-T09) for the row's actions; the kebab takes the roving `tabIndex`.
  `DataTableRowAction` is the menu's `MenuAction`.
- `IconButton` and `Button` from `button` for the expand toggle and "Clear
  selection".
- `Pagination` from `navigation`, and `Skeleton*` and `InlineAlert` from
  `feedback`.

## Gallery and tests

`data-table.gallery.tsx` holds every variant and state, ending with the
1,000-row table (container scroll, every feature). Until the component gallery
(P1-T01) lands, `markup.test.tsx` snapshots each entry's markup into
`__snapshots__/markup.md` and runs the accessibility scan on each in Light,
Dark and Unstract. Behaviour and keyboard tests are in `DataTable.test.tsx`;
the pure helpers in `columns.test.tsx`.
