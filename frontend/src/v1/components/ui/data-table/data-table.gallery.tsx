import type { ReactElement } from "react";
import { DataTable } from "./DataTable";
import type { DataTableColumn, DataTableRowAction } from "./types";

/*
 * Every variant and state of the data table, for the component gallery
 * (P1-T01, not merged yet: register these there, where each entry is shown in
 * Light, Dark and Unstract). Until then markup.test.tsx renders each one,
 * snapshots its markup and runs the accessibility scan on it in all three
 * modes. The last entry is the 1,000-row table the spec's acceptance names.
 * Each table has its own label: the gallery shows them on one page, and the
 * label names each table's bulk bar and pagination.
 */

export type GalleryEntry = Readonly<{ name: string; element: ReactElement }>;

/** A deployment row, after frame A01 (1078:936). */
export type GalleryDeployment = Readonly<{
  id: string;
  name: string;
  workflow: string;
  owner: string;
  /** Days since 2026-08-01, so dates stay fixed in snapshots. */
  lastRunDay: number;
  totalRuns: number;
  failing: boolean;
}>;

const OWNERS = ["ritwik", "milan", "vikash", "jagadeeswaran", "deepak"];
const NAMES = [
  "health-monitoring API",
  "API Hub - Purchase Order API",
  "masa_cms",
  "masa_eob_extraction",
  "UCC_Formatting API",
  "forsys_ami_api",
  "invoice-parser",
];

/** `count` rows, the same every call: every seventh one is failing. */
export function galleryRows(count: number): GalleryDeployment[] {
  return Array.from({ length: count }, (_, i) => {
    const base = NAMES[i % NAMES.length];
    return {
      id: `dep-${i + 1}`,
      name:
        i < NAMES.length ? base : `${base} ${Math.floor(i / NAMES.length) + 1}`,
      workflow: `${base.toLowerCase().replaceAll(/[^a-z0-9]+/g, "_")}_workflow`,
      owner: OWNERS[(i * 3) % OWNERS.length],
      lastRunDay: (i * 7) % 31,
      totalRuns: (i * 7919) % 300_000,
      failing: i % 7 === 1,
    };
  });
}

const dateText = (day: number): string =>
  `Aug ${String(day + 1).padStart(2, "0")}, 2026`;

export const GALLERY_COLUMNS: readonly DataTableColumn<GalleryDeployment>[] = [
  {
    id: "name",
    header: "Name",
    sortKey: "name",
    width: "xl",
    cell: (row) => (
      <span className="ui:block ui:truncate ui:font-medium">{row.name}</span>
    ),
  },
  {
    id: "workflow",
    header: "Workflow",
    sortKey: "workflow",
    priority: 3,
    cell: (row) => <span className="ui:block ui:truncate">{row.workflow}</span>,
  },
  {
    id: "owner",
    header: "Owner",
    sortKey: "owner",
    priority: 2,
    width: "md",
    cell: (row) => row.owner,
  },
  {
    id: "lastRun",
    header: "Last run",
    sortKey: "lastRunDay",
    width: "lg",
    cell: (row) => (
      <span className="ui:flex ui:flex-col">
        <span>{dateText(row.lastRunDay)}</span>
        {row.failing && (
          <span className="ui:text-caption ui:text-destructive">failed</span>
        )}
      </span>
    ),
  },
  {
    id: "totalRuns",
    header: "Total runs",
    sortKey: "totalRuns",
    align: "end",
    priority: 4,
    width: "md",
    cell: (row) => row.totalRuns.toLocaleString("en-US"),
  },
];

const noop = (): void => undefined;

export const rowId = (row: GalleryDeployment): string => row.id;
export const rowLabel = (row: GalleryDeployment): string => row.name;
export const rowTone = (row: GalleryDeployment) =>
  row.failing ? ("failure" as const) : ("default" as const);

export const rowActions = (
  _row: GalleryDeployment,
): readonly DataTableRowAction[] => [
  { id: "edit", label: "Edit", onSelect: noop },
  { id: "keys", label: "Manage keys", onSelect: noop },
  { id: "delete", label: "Delete", onSelect: noop, destructive: true },
];

const detail = (row: GalleryDeployment): ReactElement => (
  <dl className="ui:m-0 ui:grid ui:grid-cols-2 ui:gap-2 ui:text-body-small">
    <dt className="ui:text-muted-foreground">Workflow</dt>
    <dd className="ui:m-0">{row.workflow}</dd>
    <dt className="ui:text-muted-foreground">Total runs</dt>
    <dd className="ui:m-0">{row.totalRuns}</dd>
  </dl>
);

const FEW = galleryRows(5);
export const THOUSAND = galleryRows(1000);

const common = {
  label: "API deployments",
  columns: GALLERY_COLUMNS,
  getRowId: rowId,
  getRowLabel: rowLabel,
} as const;

export const DATA_TABLE_GALLERY: readonly GalleryEntry[] = [
  {
    name: "rest, sorted by name",
    element: (
      <DataTable
        {...common}
        label={`API deployments (rest, sorted by name)`}
        rows={FEW}
        defaultSort={{ columnId: "name", direction: "asc" }}
      />
    ),
  },
  {
    name: "sorted descending, failure tint",
    element: (
      <DataTable
        {...common}
        label={`API deployments (sorted descending, failure tint)`}
        rows={FEW}
        getRowTone={rowTone}
        defaultSort={{ columnId: "totalRuns", direction: "desc" }}
      />
    ),
  },
  {
    name: "loading",
    element: (
      <DataTable
        {...common}
        label={`API deployments (loading)`}
        rows={[]}
        loading
        selectable
      />
    ),
  },
  {
    name: "empty",
    element: (
      <DataTable {...common} label={`API deployments (empty)`} rows={[]} />
    ),
  },
  {
    name: "no results",
    element: (
      <DataTable
        {...common}
        label={`API deployments (no results)`}
        rows={[]}
        filtered
        toolbar="Search: zz"
      />
    ),
  },
  {
    name: "error with rows",
    element: (
      <DataTable
        {...common}
        label={`API deployments (error with rows)`}
        rows={FEW}
        error={{
          title: "Could not refresh deployments",
          message: "The server did not answer. Showing the last loaded list.",
          onRetry: noop,
        }}
      />
    ),
  },
  {
    name: "partial selection with bulk bar",
    element: (
      <DataTable
        {...common}
        label={`API deployments (partial selection with bulk bar)`}
        rows={FEW}
        selectable
        defaultSelectedIds={["dep-2", "dep-3"]}
        bulkActions={() => (
          <button type="button" className="ui:cursor-pointer">
            Delete selected
          </button>
        )}
      />
    ),
  },
  {
    name: "all selected",
    element: (
      <DataTable
        {...common}
        label={`API deployments (all selected)`}
        rows={FEW}
        selectable
        defaultSelectedIds={FEW.map(rowId)}
      />
    ),
  },
  {
    name: "expanded row, row click and actions",
    element: (
      <DataTable
        {...common}
        label={`API deployments (expanded row, row click and actions)`}
        rows={FEW}
        renderExpanded={detail}
        defaultExpandedIds={["dep-1"]}
        onRowClick={noop}
        rowActions={rowActions}
      />
    ),
  },
  {
    name: "client pagination with footer",
    element: (
      <DataTable
        {...common}
        label={`API deployments (client pagination with footer)`}
        rows={galleryRows(30)}
        pagination={{ mode: "client", pageSize: 10 }}
        footer="Updated 2 min ago"
      />
    ),
  },
  {
    name: "server pagination",
    element: (
      <DataTable
        {...common}
        label={`API deployments (server pagination)`}
        rows={FEW}
        pagination={{
          mode: "server",
          page: 2,
          pageSize: 5,
          total: 333,
          onPageChange: noop,
        }}
      />
    ),
  },
  {
    name: "1,000 rows, every feature, container scroll",
    element: (
      <DataTable
        {...common}
        label={`API deployments (1,000 rows, every feature, container scroll)`}
        rows={THOUSAND}
        scroll="container"
        className="ui:h-160"
        selectable
        defaultSelectedIds={["dep-3"]}
        bulkActions={({ clearSelection }) => (
          <button
            type="button"
            className="ui:cursor-pointer"
            onClick={clearSelection}
          >
            Abort selected
          </button>
        )}
        renderExpanded={detail}
        onRowClick={noop}
        rowActions={rowActions}
        getRowTone={rowTone}
        defaultSort={{ columnId: "lastRun", direction: "desc" }}
        toolbar="1,000 deployments"
      />
    ),
  },
];
