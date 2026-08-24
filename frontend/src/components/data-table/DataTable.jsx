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
  const id = String(c.key ?? c.dataIndex ?? path);
  const meta = { align: c.align, width: c.width, className: c.className };

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
    accessorKey: c.dataIndex,
    header: c.title,
    enableSorting: Boolean(c.sorter),
    meta,
    cell: ({ row }) => {
      const value = c.dataIndex ? row.original?.[c.dataIndex] : undefined;
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
  className,
  emptyText = "No data",
  ...props
}) {
  const [sorting, setSorting] = React.useState([]);
  const [selection, setSelection] = React.useState({});

  const data = React.useMemo(() => dataSource ?? [], [dataSource]);
  const cols = React.useMemo(
    () => toColumns(columns, rowSelection),
    [columns, rowSelection],
  );

  // antd reads `scroll.x === true` as "as wide as the content needs".
  const scrollX = scroll?.x === true ? "max-content" : scroll?.x;
  const scrollY = scroll?.y;

  // antd accepts `pagination={false}` to disable, or an object to configure.
  const paginated = pagination !== false;
  const pageSize = pagination?.pageSize ?? 10;

  const table = useReactTable({
    data,
    columns: cols,
    state: { sorting, rowSelection: selection },
    onSortingChange: setSorting,
    onRowSelectionChange: setSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    ...(paginated ? { getPaginationRowModel: getPaginationRowModel() } : {}),
    initialState: paginated ? { pagination: { pageSize } } : undefined,
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
          className={cn(size === "small" && "text-sm")}
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
                          <span className="inline-flex items-center gap-1">
                            {flexRender(
                              header.column.columnDef.header,
                              header.getContext(),
                            )}
                            {sorted === "asc" ? (
                              <ChevronUp className="size-3" />
                            ) : null}
                            {sorted === "desc" ? (
                              <ChevronDown className="size-3" />
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
                  {typeof emptyText === "string" ? (
                    <Empty description={emptyText} />
                  ) : (
                    emptyText
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
      {paginated &&
      table.getPageCount() > (pagination?.hideOnSinglePage ? 1 : 0) ? (
        /*
         * antd's pager is a 24px strip of square numbered buttons with 16px
         * margins, right-aligned. The "Previous / Page 1 of 1 / Next" text row
         * this replaces stood 56px tall and read as a different component
         * beside the reference.
         */
        <div className="ant-pagination my-4 flex items-center justify-end gap-2 text-sm">
          <PagerButton
            label="Previous page"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            <ChevronLeft className="size-3" />
          </PagerButton>
          {pageNumbers(
            table.getState().pagination.pageIndex + 1,
            table.getPageCount(),
          ).map((page, i) =>
            page === "…" ? (
              // Keyed by position: the ellipsis carries no identity of its own.
              <span key={`gap-${i}`} className="w-6 text-center">
                …
              </span>
            ) : (
              <PagerButton
                key={page}
                label={`Page ${page}`}
                active={page === table.getState().pagination.pageIndex + 1}
                onClick={() => table.setPageIndex(page - 1)}
              >
                {page}
              </PagerButton>
            ),
          )}
          <PagerButton
            label="Next page"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            <ChevronRight className="size-3" />
          </PagerButton>
        </div>
      ) : null}
    </div>
  );
}

export { DataTable };
