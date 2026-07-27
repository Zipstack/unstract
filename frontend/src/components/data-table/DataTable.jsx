import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ChevronDown, ChevronUp } from "lucide-react";
import * as React from "react";

import { Checkbox } from "@/components/ui/checkbox";
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

/** antd column defs → TanStack column defs. */
function toColumns(antdColumns = [], rowSelection) {
  const cols = antdColumns.filter(Boolean).map((c, i) => ({
    id: String(c.key ?? c.dataIndex ?? i),
    accessorKey: c.dataIndex,
    header: c.title,
    enableSorting: Boolean(c.sorter),
    meta: { align: c.align, width: c.width, className: c.className },
    cell: ({ row }) => {
      const value = c.dataIndex ? row.original?.[c.dataIndex] : undefined;
      // antd's render(value, record, index) contract.
      return c.render ? c.render(value, row.original, row.index) : value;
    },
  }));

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

function DataTable({
  columns,
  dataSource,
  rowKey = "id",
  rowSelection,
  pagination,
  loading,
  size,
  rowClassName,
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

  // Mirror selection back through antd's callback shape.
  React.useEffect(() => {
    if (!rowSelection?.onChange) {
      return;
    }
    const rows = table.getSelectedRowModel().rows.map((r) => r.original);
    rowSelection.onChange(
      rows.map((r) => r?.[typeof rowKey === "function" ? "id" : rowKey]),
      rows,
    );
  }, [selection, rowSelection, rowKey, table]);

  // antd accepts `loading` as a boolean or `{ spinning }`.
  const isLoading =
    typeof loading === "object" ? Boolean(loading?.spinning) : Boolean(loading);

  return (
    // ant-table-* class names are emitted deliberately: the app has ~12 CSS
    // rules targeting these (heights, sticky headers, overflow) that would
    // otherwise match nothing.
    <div className={cn("ant-table-wrapper w-full", className)} {...props}>
      <div className="ant-table ant-table-container">
        <Table className={cn(size === "small" && "text-sm")}>
          <TableHeader className="ant-table-thead">
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((header) => {
                  const sorted = header.column.getIsSorted();
                  return (
                    <TableHead
                      key={header.id}
                      style={{ width: header.column.columnDef.meta?.width }}
                      className={cn(
                        header.column.columnDef.meta?.align === "center" &&
                          "text-center",
                        header.column.columnDef.meta?.align === "right" &&
                          "text-right",
                        header.column.getCanSort() &&
                          "cursor-pointer select-none",
                      )}
                      onClick={header.column.getToggleSortingHandler()}
                    >
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
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody className="ant-table-tbody ant-table-body">
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={cols.length} className="h-24 text-center">
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
              <TableRow>
                <TableCell
                  colSpan={cols.length}
                  className="h-24 text-center text-muted-foreground"
                >
                  {emptyText}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {paginated && table.getPageCount() > 1 ? (
        <div className="flex items-center justify-end gap-2 py-3 text-sm">
          <button
            type="button"
            className="rounded-md border px-2 py-1 disabled:opacity-50"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            Previous
          </button>
          <span className="text-muted-foreground">
            Page {table.getState().pagination.pageIndex + 1} of{" "}
            {table.getPageCount()}
          </span>
          <button
            type="button"
            className="rounded-md border px-2 py-1 disabled:opacity-50"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  );
}

export { DataTable };
