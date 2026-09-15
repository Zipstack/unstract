import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
} from "lucide-react";
import * as React from "react";
import { ColumnFilter, columnKey } from "@/components/data-table/ColumnFilter";
import { Checkbox } from "@/components/ui/checkbox";
import { Empty } from "@/components/ui/shims/antd-leaves";
import { Spinner } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

/**
 * Shared data table (P4-02, D5 / D9).
 *
 * shadcn's `table` is presentational only, so sorting, pagination and row
 * selection come from TanStack. This wrapper presents **antd's `Table` API**
 * (`columns`, `dataSource`, `rowKey`, `rowSelection`, `pagination`, `loading`)
 * so the 16 OSS call-sites — and the cloud plugin sites in Phase C — convert by
 * import rather than by rewriting each table.
 *
 * Per D9 this is the single table implementation for both repos: plugins must
 * import it rather than build their own.
 */

/**
 * One cell's value, read the way antd reads it.
 *
 * `dataIndex` is either a key or a PATH: `["product", "name"]` is antd's
 * documented nested form and means `record.product.name`. The flat lookup this
 * replaces indexed the record with the array itself, and JavaScript stringifies
 * that to the property name `"product,name"` — so the value was always
 * undefined, and silently so, because a column with no `render` hands it
 * straight to the cell. LLMWhisperer's API Keys table declares its Plan column
 * exactly that way and lost the whole column to a blank strip.
 */
function cellValue(record, dataIndex) {
  if (Array.isArray(dataIndex)) {
    return dataIndex.reduce((v, k) => (v == null ? undefined : v[k]), record);
  }
  return record?.[dataIndex];
}

/**
 * One antd column → one TanStack column def.
 *
 * antd spells a banded header as a column that carries a `title` and a
 * `children` array instead of a `dataIndex`; the leaves under it are the real
 * columns. Ignoring `children` collapsed the whole band to a single leaf whose
 * accessor was undefined, so the LLMWhisperer processing-modes table rendered
 * its group title above sixteen blank rows — a header with no table under it.
 *
 * `path` only supplies the id for a column with neither `key` nor `dataIndex`:
 * child indices restart at 0 inside every band, so the plain index the flat
 * version used would collide across levels.
 */
function toColumn(c, path) {
  /*
   * Three places spell this identity, and they must agree: here, `columnKey`
   * (ColumnFilter.jsx) and `toSorterInfo` below, which matches on it to answer
   * antd's `onChange`. A PATH `dataIndex` with no `key` coerces to
   * `"product,name"` in all three, so they still agree — which is why this is
   * deliberately NOT normalised to `dataIndex.join(".")`. Tidying it here alone
   * would silently stop sorting and filtering reporting for a nested column.
   */
  const id = String(c.key ?? c.dataIndex ?? path);
  // `column` rides along so the header can render antd's filter affordance,
  // which is declared on the antd def and has no TanStack equivalent.
  const meta = {
    align: c.align,
    width: c.width,
    className: c.className,
    column: c,
  };

  if (c.children?.length) {
    return {
      id,
      header: c.title,
      meta,
      columns: c.children
        .filter(Boolean)
        .map((child, i) => toColumn(child, `${path}-${i}`)),
    };
  }

  return {
    id,
    /*
     * A path needs an accessor FUNCTION: TanStack's `accessorKey` is a single
     * key, so handing it the array repeats the same stringified-`"product,name"`
     * lookup one layer down.
     *
     * This is NOT inert. TanStack defaults every column to `sortUndefined: 1`,
     * and `getSortedRowModel` reads `row.getValue()` to apply it BEFORE it ever
     * consults `sortingFn` — so undefined-valued rows sort to the end even
     * though `sortingFn` is `() => 0`. A nested column was accidentally exempt
     * while every one of its values was undefined; with a real accessor it now
     * behaves exactly as an equivalent string column already does (verified:
     * both reorder identically on a sparse column). That quirk is pre-existing
     * and cross-cutting, not introduced here, and no nested column declares a
     * `sorter` today.
     *
     * The string case keeps `accessorKey` because it is unchanged, not because
     * its behaviour is right: TanStack deep-reads a DOTTED string while the
     * cell below reads it as a literal key, which is antd's own reading. Those
     * two disagree for `dataIndex: "a.b"`. Pre-existing on both halves, no
     * literal dotted `dataIndex` exists in either repo, and reconciling it is a
     * behaviour change beyond this fix.
     */
    ...(Array.isArray(c.dataIndex)
      ? { accessorFn: (record) => cellValue(record, c.dataIndex) }
      : { accessorKey: c.dataIndex }),
    header: c.title,
    enableSorting: Boolean(c.sorter),
    /*
     * antd reads the sorter's SHAPE: a function is a local comparator, while
     * `sorter: true` means "the server sorts this — just tell me it was
     * clicked". Both used to sort locally with TanStack's guessed comparator,
     * which got it wrong in both directions. A `localeCompare` sorter was
     * replaced by a generic one, and — worse — every `sorter: true` column
     * reordered the ten rows already on screen while the parent's `onChange`
     * never fired, so the Execution Logs list looked sorted and wasn't: the
     * rows it should have pulled from page two stayed on page two.
     */
    sortingFn:
      typeof c.sorter === "function"
        ? (a, b) => c.sorter(a.original, b.original)
        : () => 0,
    meta,
    cell: ({ row }) => {
      const value = c.dataIndex
        ? cellValue(row.original, c.dataIndex)
        : undefined;
      // antd's render(value, record, index) contract.
      return c.render ? c.render(value, row.original, row.index) : value;
    },
  };
}

/** antd column defs → TanStack column defs. */
function toColumns(antdColumns = [], rowSelection) {
  const cols = antdColumns.filter(Boolean).map((c, i) => toColumn(c, i));

  if (!rowSelection) {
    return cols;
  }

  return [
    {
      id: "__select",
      header: ({ table }) => (
        <Checkbox
          checked={table.getIsAllPageRowsSelected()}
          onCheckedChange={(v) => table.toggleAllPageRowsSelected(Boolean(v))}
          aria-label="Select all"
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(v) => row.toggleSelected(Boolean(v))}
          aria-label="Select row"
        />
      ),
      enableSorting: false,
    },
    ...cols,
  ];
}

/** Every leaf antd column, flattened out of any banded headers. */
function leafColumns(antdColumns = []) {
  return antdColumns
    .filter(Boolean)
    .flatMap((c) => (c.children?.length ? leafColumns(c.children) : [c]));
}

/** Does this column offer a filter at all? */
function isFilterable(c) {
  return Boolean(c.filters || c.filterDropdown);
}

/**
 * antd's sorter affordance: a caret pair, ALWAYS on for a sortable column.
 *
 * Only the active direction used to render, so an unsorted column looked
 * exactly like an unsortable one — on Execution Logs neither "Executed At" nor
 * "Execution Time" advertised that they sort at all, and the single chevron
 * that appeared after a click read as decoration rather than as state. antd
 * shows both carets greyed and lights the applied one, which is what makes the
 * column both discoverable and self-describing once sorted.
 */
function SortCarets({ sorted }) {
  return (
    <span
      className="ant-table-column-sorter inline-flex flex-col items-center justify-center leading-none"
      aria-hidden="true"
    >
      <ChevronUp
        className={cn(
          // The pair has to read as one control, so the carets overlap: two
          // 12px lucide icons stacked at their natural height sit a header row
          // apart.
          "-mb-[3px] size-3",
          sorted === "asc" ? "text-primary" : "text-muted-foreground/40",
        )}
      />
      <ChevronDown
        className={cn(
          "size-3",
          sorted === "desc" ? "text-primary" : "text-muted-foreground/40",
        )}
      />
    </span>
  );
}

/**
 * antd's `onChange` hands back a `filters` object with an entry for EVERY
 * filterable column, not just the active ones — LogModal indexes straight into
 * `filters.level[0]`, so a missing key is a TypeError rather than "no filter".
 *
 * The null-vs-empty split is antd's own: a column driving its own
 * `filterDropdown` reports its raw keys (`[]` when cleared), while a
 * `filters`-list column reports `null` once nothing is ticked.
 */
function toFilterInfo(cols, keysFor) {
  const info = {};
  for (const c of cols) {
    if (!isFilterable(c)) {
      continue;
    }
    const keys = keysFor(c);
    info[columnKey(c)] = c.filterDropdown ? keys : keys.length ? keys : null;
  }
  return info;
}

/** A TanStack sort entry in the shape antd's `onChange` promises. */
function toSorterInfo(sortEntry, cols) {
  if (!sortEntry) {
    return {};
  }
  const column = cols.find(
    (c) => String(c.key ?? c.dataIndex) === sortEntry.id,
  );
  return {
    column,
    columnKey: column?.key,
    field: column?.dataIndex,
    order: sortEntry.desc ? "descend" : "ascend",
  };
}

/** One 24px square in antd's pager: a page number, an arrow, or the ellipsis. */
function PagerButton({ children, label, active, ...props }) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-current={active ? "page" : undefined}
      className={cn(
        "inline-flex size-6 items-center justify-center rounded border text-xs transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-40",
        active
          ? "border-primary text-primary"
          : "border-separator hover:border-primary hover:text-primary",
      )}
      {...props}
    >
      {children}
    </button>
  );
}

/**
 * antd shows every page up to 7, then collapses the middle to an ellipsis so
 * the pager keeps a fixed width. Returns page numbers with "…" for the gaps.
 */
function pageNumbers(current, total) {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  // First and last are always reachable; the window slides around `current`.
  const from = Math.max(2, Math.min(current - 1, total - 4));
  const to = Math.min(total - 1, Math.max(current + 1, 5));
  return [
    1,
    ...(from > 2 ? ["…"] : []),
    ...Array.from({ length: to - from + 1 }, (_, i) => from + i),
    ...(to < total - 1 ? ["…"] : []),
    total,
  ];
}

function DataTable({
  columns,
  dataSource,
  rowKey = "id",
  rowSelection,
  pagination,
  loading,
  size,
  /**
   * antd's `tableLayout`, forwarded to CSS `table-layout`.
   *
   * Also load-bearing, and also silently dropped before: column `width` is
   * rendered onto the <th> only, and under the browser's default AUTO layout a
   * width is a hint, not a bound. One long unbroken description in
   * ResourceTable's Name column therefore stretched that column and pushed the
   * Actions column off the right edge. With "fixed" the declared widths win and
   * the cell's own ellipsis can finally take effect.
   */
  tableLayout,
  rowClassName,
  /**
   * antd's per-row event hook: `onRow(record, index)` returns props (usually
   * `{ onClick }`) that get spread onto the row.
   *
   * Declaring it is load-bearing. Undeclared, it fell into `...props` and was
   * spread onto the wrapper <div>, where React silently ignores an unknown
   * `onRow` attribute — so ResourceTable's rows carried
   * `rowClassName="…-clickable"` (cursor: pointer) while the click handler was
   * never wired, and Prompt Studio and Workflows became unopenable with no
   * console error to show for it.
   */
  onRow,
  /**
   * antd's Table-level `onChange(pagination, filters, sorter)` — the callback a
   * server-paged call-site listens to so it can fetch the page the user just
   * clicked.
   *
   * Declared for the same reason as `onRow` above: undeclared it fell into
   * `...props` and was spread onto the wrapper <div>, where React silently
   * ignores an unknown `onChange` attribute. ResourceTable's `handleChange`
   * therefore never ran, so on every server-paged list — LLMs, Vector DBs,
   * Embeddings, Text Extractors, Connectors — clicking a page number did
   * nothing whatsoever.
   */
  onChange,
  /**
   * antd's `showHeader`, default true.
   *
   * Declared for the same reason as `onRow` above: undeclared, it fell into
   * `...props` and was spread onto the wrapper <div>, where React not only
   * ignored it but warned about an unknown `showHeader` DOM attribute on every
   * render of the logs panel. A call site asking for `showHeader={false}` would
   * silently have got a header anyway.
   */
  showHeader = true,
  /**
   * antd's `scroll={{ x, y }}`: `y` caps the body height and pins the header
   * above it, `x` gives the table a minimum width so cramped columns overflow
   * sideways instead of squashing.
   *
   * Declared for the same reason as `onRow` and `showHeader` above — it fell
   * into `...props` and onto the wrapper <div>, so all ten call-sites asking
   * for it silently got a table that grew to its full height instead. The
   * LLMWhisperer processing-modes table asks for `y: 500` and stood 1270px
   * tall, pushing its own header off the top of the screen.
   */
  scroll,
  /**
   * antd's `bordered`: rules between every cell, plus an outer frame.
   *
   * Declared for the same reason as `onRow`, `showHeader` and `scroll` above —
   * undeclared it fell into `...props` and onto the wrapper <div>, where React
   * warned "Received `true` for a non-boolean attribute `bordered`" on every
   * render. The agentic Prompt Studio's extracted-data tables ask for it, and
   * got a borderless table plus a console error instead.
   */
  bordered = false,
  className,
  emptyText = "No data",
  /**
   * antd's `locale={{ emptyText }}` — the spelling six call-sites actually use.
   *
   * Declared for the same reason as `onRow`, `showHeader`, `scroll` and
   * `bordered` above, and it failed both ways at once: the custom empty state
   * was silently replaced by the bare "No data" default, AND the object landed
   * on the wrapper <div> as `locale="[object Object]"`. The agentic Prompt
   * Studio's status table is the visible casualty — a project with no
   * documents showed an empty box where "No documents in this project yet …
   * click Manage Documents to upload PDFs" should be.
   */
  locale,
  /**
   * antd's `sortDirections`: the orders a header cycles through.
   *
   * Declared for the same reason as `onRow`, `showHeader`, `scroll`, `bordered`
   * and `locale` above — undeclared it fell into `...props` and onto the
   * wrapper <div>, where React warned "does not recognize the `sortDirections`
   * prop on a DOM element" on every render of all four Execution Logs tables.
   * All four pass `["ascend", "descend", "ascend"]`, antd's idiom for "never
   * cycle back to unsorted": a repeated entry is what removes the third,
   * order-less state.
   */
  sortDirections,
  ...props
}) {
  const empty = locale?.emptyText ?? emptyText;
  const [sorting, setSorting] = React.useState([]);
  const [selection, setSelection] = React.useState({});

  const rows = React.useMemo(() => dataSource ?? [], [dataSource]);
  const cols = React.useMemo(
    () => toColumns(columns, rowSelection),
    [columns, rowSelection],
  );
  const leaves = React.useMemo(() => leafColumns(columns), [columns]);

  /*
   * Committed filters, keyed by antd column key. Only the uncontrolled ones
   * live here: a column passing `filteredValue` is driven by its parent, and a
   * column passing only `defaultFilteredValue` seeds from that until the user
   * touches it. Resolving all three in one place means the rest of the
   * component never has to know which kind it is looking at.
   */
  const [filterState, setFilterState] = React.useState({});
  const keysFor = React.useCallback(
    (c) => {
      if (c.filteredValue !== undefined) {
        return c.filteredValue ?? [];
      }
      const committed = filterState[columnKey(c)];
      return committed ?? c.defaultFilteredValue ?? [];
    },
    [filterState],
  );

  /*
   * antd applies `onFilter` itself: OR across the keys ticked within one
   * column, AND across columns. A column with `filters` but NO `onFilter` is
   * asking the server to do it, so it must not also be applied here — that is
   * the Execution Logs status filter, which pages on the server.
   */
  const data = React.useMemo(() => {
    const active = leaves.filter(
      (c) => typeof c.onFilter === "function" && keysFor(c).length > 0,
    );
    if (active.length === 0) {
      return rows;
    }
    return rows.filter((record) =>
      active.every((c) => keysFor(c).some((v) => c.onFilter(v, record))),
    );
  }, [rows, leaves, keysFor]);

  // antd reads `scroll.x === true` as "as wide as the content needs".
  const scrollX = scroll?.x === true ? "max-content" : scroll?.x;
  const scrollY = scroll?.y;

  // antd accepts `pagination={false}` to disable, or an object to configure.
  const paginated = pagination !== false;
  const pageSize = pagination?.pageSize ?? 10;
  /*
   * antd slices `dataSource` only when it holds MORE rows than fit on a page;
   * otherwise it renders what it was handed and lets `total` drive the pager.
   * That distinction IS server-side paging, and losing it broke every list that
   * pages on the server. ToolSettings requests `?page=1&page_size=10`, so
   * `dataSource` is 10 rows while the response's `count` — passed here as
   * `total` — says 12. Deriving the page count from `data.length` collapsed the
   * pager to a single page, so on the LLM settings screen two adapters the API
   * had already advertised via its `next` link were simply unreachable.
   */
  const clientPaged = paginated && data.length > pageSize;
  const total = pagination?.total ?? data.length;
  const pageCount = Math.max(1, Math.ceil(total / (pageSize || 1)));
  const [internalPage, setInternalPage] = React.useState(1);
  /*
   * antd: passing `current` makes the pager controlled — the parent refetches
   * and feeds the new page back down. Without it the table owns its own page.
   * Clamped so a shrinking list (a search, a delete) can't leave the pager
   * pointing past the last page with a blank body under it.
   */
  const currentPage = Math.min(pagination?.current ?? internalPage, pageCount);

  const goToPage = (page) => {
    const next = Math.min(Math.max(1, page), pageCount);
    if (next === currentPage) {
      return;
    }
    // Controlled pagers move only when the parent says so; uncontrolled ones
    // page themselves.
    if (pagination?.current === undefined) {
      setInternalPage(next);
    }
    onChange?.(
      { ...pagination, current: next, pageSize, total },
      toFilterInfo(leaves, keysFor),
      toSorterInfo(sorting[0], leaves),
    );
  };

  /*
   * Sorting and filtering both report through antd's single
   * `onChange(pagination, filters, sorter)`, and both used to report nothing at
   * all: `onSortingChange` went straight to `setSorting`, and filters had no
   * state to change. Every server-sorted and server-filtered list was inert.
   */
  const handleSortingChange = (updater) => {
    const next = typeof updater === "function" ? updater(sorting) : updater;
    setSorting(next);
    onChange?.(
      { ...pagination, current: currentPage, pageSize, total },
      toFilterInfo(leaves, keysFor),
      toSorterInfo(next[0], leaves),
    );
  };

  const commitFilter = (c, keys) => {
    const next = { ...filterState, [columnKey(c)]: keys };
    setFilterState(next);
    /*
     * The column being committed reports the keys the user just picked — even
     * when it is CONTROLLED. `filteredValue` is the parent's current value,
     * which is exactly the stale one here: reporting it back is how the parent
     * would learn nothing changed. LogModal's level filter is controlled on
     * `selectedLogLevel` and sets it from this callback, so echoing its own
     * `filteredValue` left the filter permanently stuck on "no level".
     * Every OTHER column still reports its own controlled or committed value.
     */
    const committedKey = columnKey(c);
    const nextKeysFor = (col) => {
      if (columnKey(col) === committedKey) {
        return keys;
      }
      return col.filteredValue !== undefined
        ? (col.filteredValue ?? [])
        : (next[columnKey(col)] ?? col.defaultFilteredValue ?? []);
    };
    if (pagination?.current === undefined) {
      setInternalPage(1);
    }
    onChange?.(
      // antd sends the user back to the first page when the filter changes:
      // page 4 of the old result set means nothing in the new one.
      { ...pagination, current: 1, pageSize, total },
      toFilterInfo(leaves, nextKeysFor),
      toSorterInfo(sorting[0], leaves),
    );
  };

  const table = useReactTable({
    data,
    columns: cols,
    // A repeat in the list means the cycle never reaches "unsorted"; a list
    // that leads with "descend" means the first click sorts that way.
    enableSortingRemoval: sortDirections
      ? new Set(sortDirections).size === sortDirections.length
      : true,
    /*
     * antd's first click is always ascending unless `sortDirections` leads
     * with "descend". Set here rather than per column because TanStack lets a
     * column def override the table option, and its own default is
     * descending-first for numeric columns — which silently reversed the first
     * click on every numeric column.
     */
    sortDescFirst: sortDirections?.[0] === "descend",
    state: {
      sorting,
      rowSelection: selection,
      // Only meaningful while we slice: a server-paged table is handed exactly
      // one page and must not have it sliced a second time.
      ...(clientPaged
        ? { pagination: { pageIndex: currentPage - 1, pageSize } }
        : {}),
    },
    onSortingChange: handleSortingChange,
    onRowSelectionChange: setSelection,
    /*
     * The pager below is the only thing that may change the page, so TanStack
     * deliberately gets no `onPaginationChange`.
     *
     * Wiring one back to the parent looks right and ping-pongs: TanStack calls
     * `resetPageIndex()` by itself every time `data` changes, so fetching page
     * 2 delivered new rows, which reset the index to 0, which fetched page 1
     * again — the table snapped back the instant it arrived. `autoResetPageIndex`
     * is off for the same reason; the `currentPage` clamp above already covers
     * the case it exists for, a page left pointing past a shrunken list.
     */
    autoResetPageIndex: false,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    ...(clientPaged ? { getPaginationRowModel: getPaginationRowModel() } : {}),
    getRowId: (row, index) =>
      typeof rowKey === "function"
        ? String(rowKey(row))
        : String(row?.[rowKey] ?? index),
  });

  /*
   * Held in a ref, and deliberately NOT in the effect's deps.
   *
   * antd tolerates an inline `rowSelection={{ selectedRowKeys, onChange }}`,
   * which most call-sites write — a fresh object every render. Depending on it
   * (or on `table`, likewise rebuilt each render) re-ran this effect on every
   * commit, and since it calls back into the parent's setState that is an
   * infinite loop: React #185, which crashed the File History modal outright.
   */
  const rowSelectionRef = React.useRef(rowSelection);
  rowSelectionRef.current = rowSelection;
  const tableRef = React.useRef(table);
  tableRef.current = table;

  // Mirror selection back through antd's callback shape.
  React.useEffect(() => {
    const onChange = rowSelectionRef.current?.onChange;
    if (!onChange) {
      return;
    }
    const rows = tableRef.current
      .getSelectedRowModel()
      .rows.map((r) => r.original);
    onChange(
      rows.map((r) => r?.[typeof rowKey === "function" ? "id" : rowKey]),
      rows,
    );
    // `selection` is the only real input: it changes exactly when the user
    // ticks a row, which is when antd would fire onChange.
  }, [selection, rowKey]);

  /*
   * antd renders the header as a SECOND table outside the scrolling body, so a
   * banded header stays put in full. One table can only pin rows with
   * `position: sticky`, and every row after the first has to sit below the
   * ones above it — an offset that cannot be known statically, since a header
   * row's height depends on where its titles wrap. So: measure after layout.
   */
  const headRef = React.useRef(null);
  const [headerOffsets, setHeaderOffsets] = React.useState([]);
  const headerRowCount = table.getHeaderGroups().length;
  React.useLayoutEffect(() => {
    if (!scrollY || !headRef.current) {
      return undefined;
    }
    const measure = () => {
      let top = 0;
      setHeaderOffsets(
        // `querySelectorAll` rather than `thead.rows`, which jsdom does not
        // implement — the measurement threw and took the whole table with it.
        Array.from(headRef.current.querySelectorAll("tr")).map((row) => {
          const offset = top;
          top += row.offsetHeight;
          return offset;
        }),
      );
    };
    measure();
    // Re-wrapping at a new width restacks the rows.
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [scrollY, headerRowCount]);

  // antd accepts `loading` as a boolean or `{ spinning }`.
  const isLoading =
    typeof loading === "object" ? Boolean(loading?.spinning) : Boolean(loading);

  return (
    // ant-table-* class names are emitted deliberately: the app has ~12 CSS
    // rules targeting these (heights, sticky headers, overflow) that would
    // otherwise match nothing.
    <div className={cn("ant-table-wrapper w-full", className)} {...props}>
      <div
        className={cn(
          "ant-table ant-table-container",
          /*
           * The cap goes on shadcn's own `overflow-auto` wrapper (the <div>
           * this one holds), NOT here: `position: sticky` resolves against the
           * nearest scrolling ancestor, and capping the outer div would leave
           * the inner one unscrolled — a header pinned to something that never
           * moves does not move either.
           */
          scrollY && "[&>div]:max-h-[var(--table-scroll-y)]",
        )}
        style={
          scrollY
            ? {
                "--table-scroll-y":
                  typeof scrollY === "number" ? `${scrollY}px` : scrollY,
              }
            : undefined
        }
      >
        <Table
          className={cn(
            size === "small" && "text-sm",
            bordered &&
              "ant-table-bordered border border-separator [&_td]:border-r [&_td]:border-separator [&_th]:border-r [&_th]:border-separator [&_td:last-child]:border-r-0 [&_th:last-child]:border-r-0",
          )}
          style={
            tableLayout || scrollX
              ? { tableLayout, minWidth: scrollX }
              : undefined
          }
        >
          {showHeader ? (
            <TableHeader className="ant-table-thead" ref={headRef}>
              {table.getHeaderGroups().map((hg, groupIndex) => (
                /*
                 * antd's `.ant-table-thead > tr > th` is `background: #fafafa`
                 * with a 1px #f0f0f0 bottom border (verified against the
                 * reference's own stylesheet). shadcn leaves the header
                 * transparent, so on the now-white table surface the header row
                 * was indistinguishable from the body.
                 *
                 * `hover:bg-muted` on TableRow would otherwise repaint the
                 * header on hover, so it is neutralised here.
                 */
                <TableRow
                  key={hg.id}
                  className="border-b border-separator bg-[var(--neutral-50)] hover:bg-[var(--neutral-50)]"
                >
                  {hg.headers.map((header) => {
                    const sorted = header.column.getIsSorted();
                    const antdColumn = header.column.columnDef.meta?.column;
                    const filterable = Boolean(
                      antdColumn && isFilterable(antdColumn),
                    );
                    const hasAffordance =
                      header.column.getCanSort() || filterable;
                    // A banded column's own row: antd centres the band title
                    // over the leaves it covers.
                    const isBand = header.subHeaders.length > 0;
                    return (
                      <TableHead
                        key={header.id}
                        /*
                         * A band spans its leaves, and TanStack pads the rows
                         * where a column has no parent with placeholder
                         * headers — without the span the second header row
                         * would be pushed out of alignment with the first.
                         */
                        colSpan={header.colSpan}
                        style={{
                          width: header.column.columnDef.meta?.width,
                          ...(scrollY
                            ? {
                                position: "sticky",
                                top: headerOffsets[groupIndex] ?? 0,
                              }
                            : null),
                        }}
                        className={cn(
                          /*
                           * The row's own background and bottom border belong
                           * to the <tr>, which the pinned cell leaves behind —
                           * the body would scroll through it. An inset shadow
                           * stands in for the border because a collapsed
                           * table border does not travel with a sticky cell.
                           */
                          scrollY &&
                            "z-[1] bg-[var(--neutral-50)] shadow-[inset_0_-1px_0_var(--separator)]",
                          /*
                           * shadcn's TableHead defaults to `font-medium
                           * text-muted-foreground`, which renders headers at
                           * weight 500 in grey. antd's `.ant-table-thead > th`
                           * is weight 600 at near-full opacity, so dev's column
                           * titles read as washed out beside the reference.
                           */
                          "font-semibold text-foreground",
                          isBand && "text-center",
                          header.column.columnDef.meta?.align === "center" &&
                            "text-center",
                          header.column.columnDef.meta?.align === "right" &&
                            "text-right",
                          header.column.getCanSort() &&
                            "cursor-pointer select-none",
                        )}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {header.isPlaceholder ? null : (
                          /*
                           * antd pins a column's affordances to the RIGHT edge
                           * of its header cell (`.ant-table-column-sorters` is
                           * `justify-content: space-between`), so a row of
                           * headers puts its sorters and filter icons on one
                           * vertical rule. Laying them inline after the title
                           * instead left them ragged — each one wherever its
                           * own text happened to end.
                           *
                           * The flex row is conditional because it is not free:
                           * `w-full` on a plain title would defeat the
                           * `text-center` / `text-right` alignment above.
                           */
                          <span
                            className={cn(
                              "items-center gap-1",
                              hasAffordance
                                ? "flex w-full justify-between"
                                : "inline-flex",
                            )}
                          >
                            {/*
                             * `flex-1` so a centred or right-aligned column
                             * still aligns its title — within the space the
                             * icon cluster leaves, which is what antd does
                             * (`.ant-table-column-title { flex: 1 }`). Without
                             * it the title would bunch against the left edge
                             * of every aligned sortable column.
                             */}
                            <span className="min-w-0 flex-1">
                              {flexRender(
                                header.column.columnDef.header,
                                header.getContext(),
                              )}
                            </span>
                            {hasAffordance ? (
                              <span className="inline-flex shrink-0 items-center gap-1">
                                {header.column.getCanSort() ? (
                                  <SortCarets sorted={sorted} />
                                ) : null}
                                {filterable ? (
                                  <ColumnFilter
                                    column={antdColumn}
                                    selectedKeys={keysFor(antdColumn)}
                                    onConfirm={(keys) =>
                                      commitFilter(antdColumn, keys)
                                    }
                                  />
                                ) : null}
                              </span>
                            ) : null}
                          </span>
                        )}
                      </TableHead>
                    );
                  })}
                </TableRow>
              ))}
            </TableHeader>
          ) : null}
          <TableBody className="ant-table-tbody ant-table-body">
            {isLoading ? (
              <TableRow>
                <TableCell
                  colSpan={table.getVisibleLeafColumns().length}
                  className="h-24 text-center"
                >
                  <Spinner />
                </TableCell>
              </TableRow>
            ) : table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() ? "selected" : undefined}
                  className={
                    typeof rowClassName === "function"
                      ? rowClassName(row.original, row.index)
                      : rowClassName
                  }
                  {...(onRow ? onRow(row.original, row.index) : {})}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell
                      key={cell.id}
                      className={cn(
                        cell.column.columnDef.meta?.align === "center" &&
                          "text-center",
                        cell.column.columnDef.meta?.align === "right" &&
                          "text-right",
                      )}
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow className="hover:bg-transparent">
                <TableCell
                  colSpan={table.getVisibleLeafColumns().length}
                  className="p-0"
                >
                  {/*
                   * antd renders <Empty> here — an illustration above the
                   * text — not a bare string. Emitting only `emptyText` left
                   * "No data" floating in the middle of the table with no
                   * icon, which read as a rendering failure rather than an
                   * empty state. A caller that passes its own node (an
                   * <Empty> with a custom image, say) still gets it as-is.
                   */}
                  {typeof empty === "string" ? (
                    <Empty description={empty} />
                  ) : (
                    empty
                  )}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/*
       * antd's `hideOnSinglePage` defaults to FALSE — the pager stays put on a
       * single page, which is why Manage Documents has a footer under its
       * one-row table in the reference and had none here. Hiding it also made
       * the modal's height jump as rows crossed the page-size boundary.
       */}
      {paginated && pageCount > (pagination?.hideOnSinglePage ? 1 : 0) ? (
        /*
         * antd's pager is a 24px strip of square numbered buttons with 16px
         * margins, right-aligned. The "Previous / Page 1 of 1 / Next" text row
         * this replaces stood 56px tall and read as a different component
         * beside the reference.
         */
        <div className="ant-pagination my-4 flex items-center justify-end gap-2 text-sm">
          {/*
           * antd renders `showTotal(total, range)` as a label beside the page
           * buttons. ResourceTable passes one ("Page 1 of 2 · 12 items") and it
           * never appeared, because this pager only ever read `pageSize` off
           * the `pagination` object and ignored the rest of it.
           */}
          {pagination?.showTotal ? (
            <span className="mr-2 text-muted-foreground">
              {pagination.showTotal(total, [
                total === 0 ? 0 : (currentPage - 1) * pageSize + 1,
                Math.min(currentPage * pageSize, total),
              ])}
            </span>
          ) : null}
          <PagerButton
            label="Previous page"
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage <= 1}
          >
            <ChevronLeft className="size-3" />
          </PagerButton>
          {pageNumbers(currentPage, pageCount).map((page, i) =>
            page === "…" ? (
              // Keyed by position: the ellipsis carries no identity of its own.
              <span key={`gap-${i}`} className="w-6 text-center">
                …
              </span>
            ) : (
              <PagerButton
                key={page}
                label={`Page ${page}`}
                active={page === currentPage}
                onClick={() => goToPage(page)}
              >
                {page}
              </PagerButton>
            ),
          )}
          <PagerButton
            label="Next page"
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage >= pageCount}
          >
            <ChevronRight className="size-3" />
          </PagerButton>
        </div>
      ) : null}
    </div>
  );
}

export { DataTable };
