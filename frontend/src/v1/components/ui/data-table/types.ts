import type { MenuAction } from "@v1/components/ui/menu";
import type { ReactNode } from "react";

/*
 * The public contract of the data table (P1-T11). P2-T04 (resource list
 * pages), P2-T07 (logs console) and P9-T10 (API Hub administration) build on
 * it, so a change here is a change to theirs: add, do not rename.
 */

/** What a client-side sort compares. `null` and `undefined` sort last both ways. */
export type DataTableSortValue = string | number | boolean | Date | null;

export type DataTableAlign = "start" | "center" | "end";

/**
 * Column width on the fixed table layout. Columns without one share what is
 * left. `xs` 48, `sm` 96, `md` 160, `lg` 224, `xl` 320 (space tokens).
 */
export type DataTableColumnWidth = "xs" | "sm" | "md" | "lg" | "xl";

/**
 * Which columns stay as the screen narrows, at the dev spec's breakpoints
 * (board 683:135, section 7): 1 always shows, 2 needs 1024 or wider, 3 needs
 * 1280, 4 needs 1440. Pages set priorities; the table owns the breakpoints.
 */
export type DataTableColumnPriority = 1 | 2 | 3 | 4;

export type DataTableColumn<TRow> = Readonly<{
  /** Unique within the table; what `DataTableSort.columnId` names. */
  id: string;
  /** Header text, and the column's accessible name. Drawn in overline caps. */
  header: string;
  cell: (row: TRow) => ReactNode;
  /**
   * Makes the column sortable. With client sorting, the table compares this
   * field of the row, or what the function returns. With server pagination
   * the table only reports the sort (`onSortChange`) and the page refetches.
   */
  sortKey?: (keyof TRow & string) | ((row: TRow) => DataTableSortValue);
  /** Default 1 (always shown). */
  priority?: DataTableColumnPriority;
  /** Default "start". Numbers go "end". */
  align?: DataTableAlign;
  width?: DataTableColumnWidth;
}>;

export type DataTableSortDirection = "asc" | "desc";

export type DataTableSort = Readonly<{
  columnId: string;
  direction: DataTableSortDirection;
}>;

/** A row's tint. `failure` marks a row whose last run failed or is stuck. */
export type DataTableRowTone = "default" | "failure";

/**
 * Pagination, chosen per table. `client` pages the rows it was given; `server`
 * shows the page the parent loaded, and the parent loads another on
 * `onPageChange`. Without pagination every row renders (virtualised when
 * `scroll="container"`).
 */
export type DataTablePagination =
  | Readonly<{
      mode: "client";
      /** Default 25. */
      pageSize?: number;
      pageSizeOptions?: readonly number[];
    }>
  | Readonly<{
      mode: "server";
      /** The current page, from 1. */
      page: number;
      pageSize: number;
      /** Rows across every page. */
      total: number;
      onPageChange: (page: number) => void;
      onPageSizeChange?: (pageSize: number) => void;
      pageSizeOptions?: readonly number[];
    }>;

/** What the bulk bar's actions act on. */
export type DataTableBulkContext<TRow> = Readonly<{
  selectedIds: readonly string[];
  /** The selected rows the table holds (with server pagination, those loaded). */
  selectedRows: readonly TRow[];
  clearSelection: () => void;
}>;

/**
 * One entry in a row's action menu (the kebab at the row's end): P1-T09's
 * `MenuAction` (`id`, `label`, `onSelect`, and optionally `disabled`,
 * `destructive`, `icon`, `shortcut`, `description`, `loading`, `group`).
 * Destructive actions go last, after a separator.
 */
export type DataTableRowAction = MenuAction;

export type DataTableError = Readonly<{
  title: string;
  /** The plain-language cause. */
  message?: ReactNode;
  onRetry?: () => void;
}>;

export type DataTableProps<TRow> = Readonly<{
  /** Names the table for assistive technology ("API deployments"). */
  label: string;
  columns: readonly DataTableColumn<TRow>[];
  rows: readonly TRow[];
  getRowId: (row: TRow) => string;
  /**
   * The row's name, read in its controls' accessible names ("Select
   * invoice-parser", "Actions for invoice-parser").
   */
  getRowLabel: (row: TRow) => string;

  /** Sorting: controlled with `sort`, else `defaultSort` starts it. */
  sort?: DataTableSort | null;
  defaultSort?: DataTableSort | null;
  onSortChange?: (sort: DataTableSort | null) => void;

  pagination?: DataTablePagination;

  /** Adds the checkbox column and the bulk bar. */
  selectable?: boolean;
  /** Controlled selection; leave out to let the table hold it. */
  selectedIds?: readonly string[];
  /** Uncontrolled selection's starting rows. */
  defaultSelectedIds?: readonly string[];
  onSelectionChange?: (ids: readonly string[]) => void;
  /** The bulk bar's actions, shown while any row is selected. */
  bulkActions?: (context: DataTableBulkContext<TRow>) => ReactNode;

  /** Detail shown in place under a row; adds the expand column. */
  renderExpanded?: (row: TRow) => ReactNode;
  /** Default: every row expands when `renderExpanded` is given. */
  canExpand?: (row: TRow) => boolean;
  /** Rows open at first render. */
  defaultExpandedIds?: readonly string[];

  /** The row click target: a click anywhere on the row, or Enter on it. */
  onRowClick?: (row: TRow) => void;
  rowActions?: (row: TRow) => readonly DataTableRowAction[];
  getRowTone?: (row: TRow) => DataTableRowTone;

  /** Skeleton rows instead of the body. */
  loading?: boolean;
  /** Skeleton rows while loading; default the page size, at most 10. */
  loadingRows?: number;
  /** Shown above the table; rows already loaded stay. */
  error?: DataTableError | null;
  /** True while a search or filter narrows the rows: no rows means no results. */
  filtered?: boolean;

  toolbar?: ReactNode;
  /** The empty state (no rows and nothing filtered). */
  empty?: ReactNode;
  /** The no-results state (no rows while `filtered`). */
  noResults?: ReactNode;
  /** Above the pagination, at the table's foot. */
  footer?: ReactNode;

  /**
   * `page` (default): the page scrolls and the header sticks to it.
   * `container`: the table scrolls inside its own box (give it a height with
   * `className`), and long lists render only the rows in view.
   */
  scroll?: "page" | "container";
  className?: string;
}>;
